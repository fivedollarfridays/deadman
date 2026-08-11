"""``POST /self-check``: the endpoint Cloud Scheduler triggers on a cadence.

DM1.11 built a self-check that could only prove one instance's liveness,
because it read and wrote a per-instance file. DM2.6 gives it a cadence
Cloud Run cannot skip — Cloud Scheduler, authenticated by
:mod:`deadman.scheduled.auth` — and a durable place to write, via
:class:`deadman.self_check.StoreSelfEvidenceLog`, so the claim survives a
cold start.
"""

from __future__ import annotations

from deadman.scheduled.auth import (
    AUTHORIZATION_ENVIRON_KEY,
    AUTHORIZATION_HEADER,
    SECRET_ENV,
    SchedulerAuthError,
    SchedulerNotConfigured,
    check_secret,
    secret_from_env,
)
from deadman.scheduled.endpoint import SCHEDULED_PATH, ScheduledSelfCheckEndpoint

__all__ = [
    "AUTHORIZATION_ENVIRON_KEY",
    "AUTHORIZATION_HEADER",
    "SCHEDULED_PATH",
    "SECRET_ENV",
    "ScheduledSelfCheckEndpoint",
    "SchedulerAuthError",
    "SchedulerNotConfigured",
    "check_secret",
    "secret_from_env",
]
