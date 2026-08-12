"""The caller the alarm never had.

Every piece of the alert path existed and was tested by DM2.7 —
:class:`~deadman.remediate.transports.EmailTransport`, the throttle that
never suppresses a state change, the out-of-band refusal, transport failures
becoming evidence. What did not exist was anything that *called* it: the
deployed service recorded faults faithfully and told no one, which is the
board-as-brief problem one level up. A monitor that needs to be asked is not
finished.

**The call site is the scheduled sweep**, deliberately. It already runs every
15 minutes on a clock external to this service (Cloud Scheduler), it already
reads the store, and it is already the thing whose own death is watched by
``self:sweep`` liveness — so the alarm inherits a cadence someone is
watching, rather than growing a second clock nobody watches.

**What fires:** every FAULT (collected or local), every surface gone stale,
and every declared collector that is silent or has never reported. **What
does not:** healthy rows, and the service's own permanently-blind local
probes — the container has no brief log by design, and paging a human four
times an hour about topology teaches them to delete the alarm.

**Known limit, stated:** the throttle window lives in instance memory, so a
Cloud Run cold start forgets it and a persisting fault may re-alert early.
That is a bounded repeat of a true alarm, which this project will accept;
a durable throttle is DM3 work if the repeats annoy in practice.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from deadman.evidence.model import Evidence, Observation
from deadman.remediate.alert import AlertChannel
from deadman.remediate.transports import (
    ThrottledAlertChannel,
    email_transport_from_env,
    record_transport_failures,
)
from deadman.store.base import EvidenceStore
from deadman.verify.collector_liveness import LivenessReport, collector_surface

#: Local (in-container) surfaces that are unobservable on *every* sweep by
#: topology rather than by failure. The collected path watches the real ones.
_PERMANENTLY_BLIND_LOCAL = frozenset({"cron:morning-brief"})


class AlarmUnconfigured(RuntimeError):
    """Raised when the ``DEADMAN_ALERT_*`` environment is absent or partial."""


class Alarm(Protocol):
    """What :func:`evaluate` needs: the throttled channel's alert shape."""

    def alert(self, key: str, state: str, message: str, *, now: datetime | None = None) -> None:
        """Deliver, throttled per ``(key, state)``."""


def alarm_from_env(
    store: EvidenceStore,
    monitored: Sequence[str],
    environ: Mapping[str, str] | None = None,
) -> ThrottledAlertChannel:
    """The production alarm: env-configured SMTP, out-of-band checked,
    failures recorded to the store, repeats throttled.

    Raises :class:`AlarmUnconfigured` when the environment is missing rather
    than returning a channel that silently cannot send — the caller decides
    whether an unconfigured alarm is fatal, but it may never be invisible.
    """
    source = os.environ if environ is None else environ
    try:
        transport = email_transport_from_env(source)
    except Exception as exc:
        raise AlarmUnconfigured(str(exc)) from exc

    channel = AlertChannel(
        transport=f"email:{transport.to_addr}",
        send=record_transport_failures(transport.send, store),
        monitored=list(monitored),
    )
    return ThrottledAlertChannel(channel=channel)


def evaluate(
    liveness: LivenessReport | None,
    local_evidence: Iterable[Evidence],
    channel: Alarm,
    now: datetime | None = None,
) -> int:
    """Fire the alarm for everything alertable in one sweep. Returns the
    number of alerts delivered to the channel (before throttling).

    A transport failure propagates after being recorded as evidence — the
    scheduled request then fails loudly and Cloud Scheduler's job status goes
    red, which is exactly the visibility a broken alarm deserves.
    """
    fired = 0

    if liveness is not None:
        for report in liveness.collectors:
            if report.liveness.value == "live":
                continue
            surface = collector_surface(report.expectation.collector_id)
            silent = (
                f"silent for {report.silent_for_seconds:.0f}s"
                if report.silent_for_seconds is not None
                else "has never reported"
            )
            channel.alert(
                surface,
                report.liveness.value,
                (
                    f"deadman: collector {report.expectation.collector_id} is "
                    f"{report.liveness.value} — {silent}, expected every "
                    f"{report.expectation.interval_seconds:g}s. A silent collector "
                    f"means every surface it carries is going dark."
                ),
                now=now,
            )
            fired += 1

        for row in liveness.surfaces:
            if row.observation is Observation.HEALTHY:
                continue
            channel.alert(
                row.surface,
                row.observation.value,
                f"deadman: {row.surface} is {row.observation.value} — {row.summary}",
                now=now,
            )
            fired += 1

    for row in local_evidence:
        if row.observation is Observation.FAULT:
            channel.alert(
                row.surface,
                row.observation.value,
                f"deadman: {row.surface} is {row.observation.value} — {row.summary}",
                now=now,
            )
            fired += 1

    return fired


def default_alarm(store: EvidenceStore) -> ThrottledAlertChannel | None:
    """The production alarm, or ``None`` with a loud boot warning.

    Follows the ``DEADMAN_COLLECTORS`` precedent: a missing capability warns
    on stderr rather than refusing to serve, because the ingest path must
    keep accepting evidence even while the alarm is unconfigured — but every
    scheduled trigger's response also carries ``alerting: unconfigured``, so
    the gap is visible on the job Cloud Scheduler is already watching.

    ``monitored`` is the real list — the declared collector surfaces, their
    collector rails, and the service's own probes — so wiring the alarm onto
    a watched rail dies here at startup, not at the moment it is needed. The
    service import is lazy for the same reason ``real_monitored_surfaces``'s
    is: this module must stay importable without the service's env.
    """
    import sys

    from deadman.service import default_expectations, default_probes

    expectations = default_expectations()
    monitored = [probe.surface for probe in default_probes()]
    for expectation in expectations:
        monitored.append(collector_surface(expectation.collector_id))
        monitored.extend(expectation.surfaces)
    try:
        return alarm_from_env(store=store, monitored=monitored)
    except AlarmUnconfigured as exc:
        print(
            f"deadman: the alarm is UNCONFIGURED, so faults will be recorded and "
            f"nobody will be told — the board-as-brief failure this project exists "
            f"to end. {exc}",
            file=sys.stderr,
        )
        return None
