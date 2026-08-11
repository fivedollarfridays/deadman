"""A real transport for :class:`~deadman.remediate.alert.AlertChannel`.

DM1.11 built the out-of-band refusal but wired nothing real to it: the
"monitored" list in its own tests was a hand-typed literal that could drift
from what is actually watched, and a failed send had nowhere to go but an
uncaught exception. This module closes both gaps.

**Email over the same rail the ops repo already uses.** ``smtplib`` and
``email.message`` are both stdlib, so this needs no optional extra —
``pyproject.toml`` keeps ``dependencies = []``. The SMTP shape below
(STARTTLS, then login, then ``send_message``) matches
``ops/lib/email_send.py``: this is meant to go out over the same mailbox,
not a second one to configure and forget.

**The monitored list is read from the real probes, never retyped.**
:func:`real_monitored_surfaces` asks :mod:`deadman.service` for the exact
probe list the board runs, so a surface added there is automatically out of
bounds for the alarm — nobody has to remember to update a second list by
hand.

**A throttle that cannot swallow a state change.** A persistent fault
sweeps on every cadence, and resending an unchanged fault every time is
alarm-fatigue-by-design. But a transition — fault to healthy or healthy to
fault — is the one thing this whole project exists to surface, so
:class:`ThrottledAlertChannel` only ever suppresses a *repeat* of the
previous state, never a change from it.

**A transport failure becomes evidence, not silence.**
:func:`record_transport_failures` wraps a ``send`` callable so a raised
exception is appended to the evidence store before it propagates. The
exception still propagates — :meth:`AlertChannel.alert`'s contract is that a
swallowed alert is silence, and recording a trace does not relax that.
"""

from __future__ import annotations

import os
import smtplib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

from deadman.evidence.model import Evidence, Method, Observation
from deadman.remediate.alert import AlertChannel
from deadman.store.base import EvidenceStore

#: One line, no config: the alert body is the whole message and nothing in
#: this project reads a subject line programmatically.
DEFAULT_SUBJECT = "deadman alert"

#: A persistent fault sweeps on every cadence; without a floor here, an
#: unwatched interval sweep would resend the same fault every run. An hour
#: is long enough to stop that and short enough that a human still hears
#: about a real, ongoing fault well inside a working day.
DEFAULT_THROTTLE_WINDOW = timedelta(hours=1)

#: Where a failed alert attempt is recorded. Distinct from every monitored
#: surface's own rail id so it can never collide with the out-of-band check.
ALERT_TRANSPORT_FAILURE_SURFACE = "alert:email"

_FAILURE_SOURCE = "remediate:transports"

_REQUIRED_ENV_VARS = (
    "DEADMAN_ALERT_SMTP_HOST",
    "DEADMAN_ALERT_SMTP_PORT",
    "DEADMAN_ALERT_SMTP_USER",
    "DEADMAN_ALERT_SMTP_PASSWORD",
    "DEADMAN_ALERT_FROM",
    "DEADMAN_ALERT_TO",
)


class EmailTransportNotConfigured(RuntimeError):
    """Raised at construction when the ops SMTP rail has no credentials."""


@dataclass
class EmailTransport:
    """Sends one alert as one plain-text email over SMTP with STARTTLS."""

    host: str
    port: int
    username: str
    password: str
    from_addr: str
    to_addr: str
    subject: str = DEFAULT_SUBJECT
    smtp_cls: Any = None
    """Injected only by the test suite (a double that opens no socket). Left
    ``None`` in real use, where :class:`smtplib.SMTP` is constructed
    directly — the same seam :class:`~deadman.store.firestore.FirestoreEvidenceStore`
    uses for its client."""

    def send(self, message: str) -> None:
        """Send. Raises on any transport failure; never swallows one."""
        msg = EmailMessage()
        msg["Subject"] = self.subject
        msg["From"] = self.from_addr
        msg["To"] = self.to_addr
        msg.set_content(message)

        smtp_cls = self.smtp_cls or smtplib.SMTP
        with smtp_cls(self.host, self.port, timeout=30) as connection:
            connection.starttls()
            connection.login(self.username, self.password)
            connection.send_message(msg)


def email_transport_from_env(environ: Mapping[str, str] | None = None) -> EmailTransport:
    """Build an :class:`EmailTransport` from ``DEADMAN_ALERT_*``, or refuse.

    Reads ``os.environ`` by default; the parameter exists so tests can pin
    the missing-variable case without mutating global state, matching
    :func:`deadman.ingest.auth.secret_from_env`.
    """
    source = os.environ if environ is None else environ
    missing = [name for name in _REQUIRED_ENV_VARS if not source.get(name, "").strip()]
    if missing:
        raise EmailTransportNotConfigured(
            f"{', '.join(missing)} not set, so the alarm has no email rail to send "
            f"over. Set every DEADMAN_ALERT_* variable to the ops SMTP rail's values."
        )
    return EmailTransport(
        host=source["DEADMAN_ALERT_SMTP_HOST"],
        port=int(source["DEADMAN_ALERT_SMTP_PORT"]),
        username=source["DEADMAN_ALERT_SMTP_USER"],
        password=source["DEADMAN_ALERT_SMTP_PASSWORD"],
        from_addr=source["DEADMAN_ALERT_FROM"],
        to_addr=source["DEADMAN_ALERT_TO"],
    )


def real_monitored_surfaces() -> list[str]:
    """The surfaces deadman actually watches right now.

    Read from :func:`deadman.service.default_probes` — the exact list the
    board sweeps — rather than retyped as a literal that can silently drift
    out of sync with what is actually monitored. Imported lazily so this
    module stays cheap to import for callers that only want the transport or
    the throttle.
    """
    from deadman.service import default_probes

    return [probe.surface for probe in default_probes()]


def record_transport_failures(
    send: Callable[[str], None],
    store: EvidenceStore,
    *,
    surface: str = ALERT_TRANSPORT_FAILURE_SURFACE,
    source: str = _FAILURE_SOURCE,
) -> Callable[[str], None]:
    """Wrap ``send`` so a failure is recorded before it propagates.

    The exception still raises. Recording the failure is additional, not a
    substitute for :meth:`AlertChannel.alert`'s own "failures propagate"
    contract — a caller that only records and never raises would have turned
    a broken alarm into a quiet log line.
    """

    def wrapped(message: str) -> None:
        try:
            send(message)
        except Exception as exc:
            store.append(
                Evidence(
                    surface=surface,
                    observation=Observation.FAULT,
                    method=Method.ACTIVE_CANARY,
                    summary=f"alert transport failed: {type(exc).__name__}: {exc}",
                    source=source,
                    detail={"message": message, "error": str(exc)},
                )
            )
            raise

    return wrapped


@dataclass
class ThrottledAlertChannel:
    """Suppresses a repeat of the same state inside a window; a state change
    is delivered immediately regardless of how recently the last alert
    fired.

    ``key`` scopes the window per caller (e.g. per surface, or "self_check")
    so two unrelated alarms never share one throttle clock.
    """

    channel: AlertChannel
    window: timedelta = DEFAULT_THROTTLE_WINDOW
    _last: dict[str, tuple[str, datetime]] = field(default_factory=dict, init=False, repr=False)

    def alert(self, key: str, state: str, message: str, *, now: datetime | None = None) -> None:
        moment = now or datetime.now(timezone.utc)
        prior = self._last.get(key)
        if prior is not None:
            prior_state, prior_sent = prior
            if state == prior_state and moment - prior_sent < self.window:
                return
        self.channel.alert(message)
        self._last[key] = (state, moment)
