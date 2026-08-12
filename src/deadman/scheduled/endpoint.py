"""``POST /self-check``: the endpoint Cloud Scheduler triggers.

Separate from ``GET /`` on purpose (see :mod:`deadman.scheduled.auth`'s module
docstring for why) and separate from ``POST /evidence`` too — that path takes
evidence a collector already gathered; this one runs the sweep itself, on a
cadence the deployment controls rather than one driven by inbound requests.

**Liveness is read before the sweep, not after.** Read the prior row, sweep,
then write: reading `after` writing would always answer LIVE, because the row
just written is by definition fresh, and a self-check that cannot fail is not
a self-check. What ``liveness_before`` in the response actually catches is a
gap in the *cadence itself* — Cloud Scheduler stopped firing, or the last few
triggers all failed before reaching this line — which only shows up by asking
"was the *previous* row still fresh" before this one is written.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from deadman.probes.base import Probe, blind_spots, sweep
from deadman.scheduled.alerting import Alarm, evaluate
from deadman.scheduled.auth import AUTHORIZATION_ENVIRON_KEY, SchedulerAuthError, check_secret
from deadman.self_check import DEFAULT_WINDOW_HOURS, StoreSelfEvidenceLog, self_check
from deadman.verify.collector_liveness import LivenessReport

#: The path Cloud Scheduler posts to.
SCHEDULED_PATH = "/self-check"

ProbesFn = Callable[[], list[Probe]]

_STATUS_UNAUTHORIZED = "401 Unauthorized"
_STATUS_OK = "200 OK"


@dataclass
class ScheduledSelfCheckEndpoint:
    """Handles one ``POST /self-check``, writing through a
    :class:`~deadman.self_check.StoreSelfEvidenceLog`."""

    probes_fn: ProbesFn
    self_log: StoreSelfEvidenceLog
    secret: str
    window_hours: float = DEFAULT_WINDOW_HOURS
    alarm: Alarm | None = None
    """The throttled alert channel, or ``None`` when ``DEADMAN_ALERT_*`` is
    unconfigured. Optional follows the ``DEADMAN_COLLECTORS`` precedent — a
    capability gap warns loudly at boot rather than refusing to serve — but
    the response names the gap on every trigger so it cannot be quiet."""
    liveness_fn: Callable[[], LivenessReport | None] | None = None

    def handle(self, environ: dict) -> tuple[str, dict[str, Any]]:
        """``(status, payload)`` for one request. Never raises for bad input."""
        try:
            check_secret(environ.get(AUTHORIZATION_ENVIRON_KEY), self.secret)
        except SchedulerAuthError as exc:
            return _STATUS_UNAUTHORIZED, {"error": str(exc)}

        before = self_check(self.self_log, window_hours=self.window_hours)

        evidence = sweep(self.probes_fn())
        blind = blind_spots(evidence)
        # Self-evidence is recorded BEFORE the alarm runs: a failing alert
        # transport must not erase the fact that this sweep happened, or the
        # self-liveness alarm would fire on top of the transport failure and
        # the two faults would be indistinguishable.
        self.self_log.record(sweep_size=len(evidence), blind=len(blind))

        payload: dict[str, Any] = {
            "liveness_before": before.liveness.value,
            "sweep_size": len(evidence),
            "blind_count": len(blind),
        }
        if self.alarm is None:
            payload["alerting"] = "unconfigured"
        else:
            liveness = self.liveness_fn() if self.liveness_fn is not None else None
            payload["alerts_evaluated"] = evaluate(liveness, evidence, self.alarm)
            payload["alerting"] = "active"
        return _STATUS_OK, payload
