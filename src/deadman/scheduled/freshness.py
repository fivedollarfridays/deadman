"""How old the scheduled self-check is, published for a reader on another clock.

Every alarm this service sends runs inside ``POST /self-check``, and only
Cloud Scheduler calls that. So the service cannot notice its own scheduler
stopping: the code that would notice is the code that stopped running. The
self-check's record (``self:sweep``) therefore has to be judged by something
that does not share that clock.

This module is the service's half of that arrangement. It reads the newest
``self:sweep`` row and renders it as the board's ``self_check`` field, whose
shape is a contract with the independent watcher (see ``infra/scheduler.md``,
"Who watches the scheduler"):

- ``surface``: always ``self:sweep``.
- ``liveness``: ``live``, ``stale`` or ``no_evidence`` (never recorded, or
  the record could not be read); anything but ``live`` means the alarm path
  is not proven to have run inside the window, and a watcher alarms.
- ``last_run_at``: ISO-8601 instant of the newest completed scheduled sweep,
  or ``null`` if none has ever been recorded.
- ``age_seconds``: seconds since ``last_run_at`` when the board was built, or
  ``null``.
- ``window_seconds``: the staleness window, :data:`WINDOW_SECONDS`.
- ``interval_seconds``: the declared scheduler cadence.

**The window is three scheduler intervals.** One missed firing, plus the
trigger's own latency, is lateness; two consecutive misses are an incident.
The window this used to share with the daily self-check CLI was 30 hours,
which read a scheduler dead for a day as live.
"""

from __future__ import annotations

from datetime import datetime, timezone

from deadman.self_check import SELF_CHECK_SURFACE, Liveness, StoreSelfEvidenceLog, self_check
from deadman.store.base import EvidenceStore

#: The Cloud Scheduler job's cadence (``*/15 * * * *``, infra/scheduler.md).
SCHEDULER_INTERVAL_SECONDS = 900

#: How many intervals of silence the self-check tolerates before it is stale.
WINDOW_INTERVALS = 3

WINDOW_SECONDS = SCHEDULER_INTERVAL_SECONDS * WINDOW_INTERVALS

#: The same window in the unit :func:`deadman.self_check.self_check` takes.
WINDOW_HOURS = WINDOW_SECONDS / 3600.0


def board_field(store: EvidenceStore | None, now: datetime | None = None) -> dict[str, object]:
    """The board's ``self_check`` object. ``store`` is ``None`` only for a
    board built without one (a local sweep, the sample generator), which has
    no scheduled record to read and says so as ``no_evidence``."""
    field: dict[str, object] = {
        "surface": SELF_CHECK_SURFACE,
        "liveness": Liveness.NO_EVIDENCE.value,
        "last_run_at": None,
        "age_seconds": None,
        "window_seconds": WINDOW_SECONDS,
        "interval_seconds": SCHEDULER_INTERVAL_SECONDS,
    }
    if store is None:
        return field
    moment = now or datetime.now(timezone.utc)
    try:
        result = self_check(
            StoreSelfEvidenceLog(store=store), window_hours=WINDOW_HOURS, now=moment
        )
        last = result.detail.get("last_sweep_at")
        age = moment - datetime.fromisoformat(last) if isinstance(last, str) else None
    except Exception:  # noqa: BLE001 — any unreadable record is the loud state
        # A store hiccup or a malformed row must not blank the public board;
        # it reads ``no_evidence``, which the watcher treats as an alarm.
        return field
    field["liveness"] = result.liveness.value
    if age is not None:
        field["last_run_at"] = last
        field["age_seconds"] = round(age.total_seconds(), 1)
    return field
