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
from deadman.scheduled.auth import AUTHORIZATION_ENVIRON_KEY, SchedulerAuthError, check_secret
from deadman.self_check import DEFAULT_WINDOW_HOURS, StoreSelfEvidenceLog, self_check

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

    def handle(self, environ: dict) -> tuple[str, dict[str, Any]]:
        """``(status, payload)`` for one request. Never raises for bad input."""
        try:
            check_secret(environ.get(AUTHORIZATION_ENVIRON_KEY), self.secret)
        except SchedulerAuthError as exc:
            return _STATUS_UNAUTHORIZED, {"error": str(exc)}

        before = self_check(self.self_log, window_hours=self.window_hours)

        evidence = sweep(self.probes_fn())
        blind = blind_spots(evidence)
        self.self_log.record(sweep_size=len(evidence), blind=len(blind))

        return _STATUS_OK, {
            "liveness_before": before.liveness.value,
            "sweep_size": len(evidence),
            "blind_count": len(blind),
        }
