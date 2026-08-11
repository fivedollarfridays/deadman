"""Who may write to the estate's record, and for how long a signature counts.

**The MAC covers the raw request bytes.** Not a re-serialisation of the parsed
payload, which would make verification depend on this service and the
collector agreeing on canonical JSON forever, and not a subset of fields,
which would leave the rest editable in transit. Bytes in, bytes verified, then
parsed — in that order, so nothing unauthenticated is ever interpreted.

**``signed_at`` lives inside those bytes**, which is what makes the freshness
window mean something. A timestamp in a header sits outside the MAC and can be
rewritten by whoever captured the body, so the check it feeds would be
decorative.

**The window is bounded in both directions.** Only refusing old signatures
leaves a captured body replayable forever by dating it forward. Note what the
window is and is not for: it bounds how long stolen bytes stay useful. It is
*not* the replay defence for an honest collector re-sending a spool it could
not deliver — that is idempotency's job (:mod:`deadman.ingest.arrival`), and
the two must not be confused, because a service that refused honest retries
would drop evidence exactly when the network was already unreliable.

**A missing secret is a refusal, not a default.** ``secret_from_env`` raises,
:mod:`deadman.service` calls it at import, and the process therefore dies at
startup rather than serving an endpoint that accepts anything. The alternative
failure — an unconfigured deploy quietly trusting every caller who can reach
the URL — produces a board that looks like a monitored estate and is in fact a
guestbook.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from deadman.store.base import instant

#: Environment variable holding the shared secret. The name is in the source;
#: the value never is.
SECRET_ENV = "DEADMAN_INGEST_SECRET"

#: Header carrying the hex MAC of the request body.
SIGNATURE_HEADER = "X-Deadman-Signature"

#: The WSGI spelling of :data:`SIGNATURE_HEADER`.
SIGNATURE_ENVIRON_KEY = "HTTP_X_DEADMAN_SIGNATURE"

#: How far ``signed_at`` may sit from the service's clock, in either
#: direction. Five minutes absorbs ordinary NTP drift between a laptop and
#: Cloud Run while keeping captured bytes short-lived.
FRESHNESS_SECONDS = 300


class AuthError(Exception):
    """The batch is not from someone entitled to write, or not from recently.

    Carries no detail about *which* check failed beyond a short reason,
    because the endpoint returns this reason to the caller and a precise
    oracle would help someone tune an attack.
    """


class IngestNotConfigured(RuntimeError):
    """No shared secret is configured. Raised at startup, never at request time."""


_MISSING_SECRET = (
    f"{SECRET_ENV} is not set, so ingest cannot tell a collector from anyone "
    f"else who can reach this URL. Refusing to start rather than accepting "
    f"unsigned batches. Set {SECRET_ENV} to the same value the collector signs with."
)


def secret_from_env(environ: Mapping[str, str] | None = None) -> bytes:
    """The shared secret, or a refusal.

    Reads ``os.environ`` by default; the parameter exists so tests can pin the
    absent case without mutating global state.
    """
    source = os.environ if environ is None else environ
    value = source.get(SECRET_ENV, "")
    if not value.strip():
        raise IngestNotConfigured(_MISSING_SECRET)
    return value.encode("utf-8")


def sign(body: bytes, secret: bytes) -> str:
    """The hex MAC a collector puts in :data:`SIGNATURE_HEADER`."""
    return hmac.new(secret, body, sha256).hexdigest()


def verify(
    body: bytes,
    signature: str | None,
    secret: bytes,
    signed_at: datetime,
    now: datetime | None = None,
) -> None:
    """Raise :class:`AuthError` unless ``body`` is signed and fresh.

    Returns ``None`` on success rather than a truthy value: a caller who
    forgets to check a boolean gets a silent pass, whereas a caller who
    forgets to catch an exception gets a 500 they will notice.

    The endpoint calls the two checks separately, because ``signed_at`` lives
    inside the body and the body must not be parsed until it has been
    authenticated.
    """
    check_signature(body, signature, secret)
    check_freshness(signed_at, now)


def check_signature(body: bytes, signature: str | None, secret: bytes) -> None:
    """Raise :class:`AuthError` unless ``body`` carries a valid MAC.

    ``hmac.compare_digest`` raises ``TypeError`` when either ``str`` argument
    contains a non-ASCII character, and WSGI hands header values through as
    latin-1 ``str``. A header of ``ü`` therefore used to reach an unhandled
    exception from an unauthenticated caller. A signature that is not ASCII
    hex cannot be a valid MAC, so it is refused as one rather than crashed on.
    """
    if signature is None or not signature.strip():
        raise AuthError("missing signature")
    candidate = signature.strip().lower()
    if not candidate.isascii():
        raise AuthError("signature does not match")
    if not hmac.compare_digest(sign(body, secret), candidate):
        raise AuthError("signature does not match")


def check_freshness(signed_at: datetime, now: datetime | None = None) -> None:
    """Raise :class:`AuthError` unless ``signed_at`` is inside the window."""
    moment = instant(now) if now is not None else datetime.now(timezone.utc)
    skew = abs(instant(signed_at) - moment)
    if skew > timedelta(seconds=FRESHNESS_SECONDS):
        raise AuthError(
            f"stale signature: signed_at is {int(skew.total_seconds())}s from this "
            f"service's clock, the window is {FRESHNESS_SECONDS}s"
        )
