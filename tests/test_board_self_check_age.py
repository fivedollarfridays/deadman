"""A stopped scheduler is visible on the board, to a reader on its own clock.

Audit findings D1 and C3. Every alarm runs inside ``POST /self-check``, which
only Cloud Scheduler calls. The self-check writes ``self:sweep``, but nothing
judged it: it sat in ``undeclared_surfaces``, and its only reader was the next
trigger, which never comes if the scheduler stops or its secret breaks. Its
window was 30 hours for a 15-minute job. So a dead scheduler disabled every
alarm while the board stayed green.

The fix does not make the service watch itself (it cannot: it only runs when
the scheduler it would be judging calls it). It publishes the self-check's
last-run instant and age on the public board as ``self_check``, judged against
three scheduler intervals, for a watcher on an independent clock to alarm on.
These tests read that field through ``GET /`` on the app the service serves,
with the self-check row written by the real scheduled endpoint's writer.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

from conftest import TEST_SCHEDULER_SECRET

from deadman.scheduled.auth import AUTHORIZATION_ENVIRON_KEY
from deadman.scheduled.endpoint import SCHEDULED_PATH, ScheduledSelfCheckEndpoint
from deadman.scheduled.freshness import SCHEDULER_INTERVAL_SECONDS, WINDOW_SECONDS
from deadman.self_check import StoreSelfEvidenceLog
from deadman.service import make_app
from deadman.store.memory import InMemoryEvidenceStore

CONTRACT_KEYS = {
    "surface",
    "liveness",
    "last_run_at",
    "age_seconds",
    "window_seconds",
    "interval_seconds",
}


def _call(app, path: str = "/", method: str = "GET", **extra: object) -> tuple[str, dict]:
    captured: dict[str, str] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status

    environ: dict[str, object] = {"PATH_INFO": path, "REQUEST_METHOD": method}
    environ["wsgi.input"] = io.BytesIO(b"")
    environ.update(extra)
    body = b"".join(app(environ, start_response))
    return captured["status"], json.loads(body)


def _service(store: InMemoryEvidenceStore):
    scheduled = ScheduledSelfCheckEndpoint(
        probes_fn=lambda: [],
        self_log=StoreSelfEvidenceLog(store=store),
        secret=TEST_SCHEDULER_SECRET,
    )
    return make_app(lambda: [], scheduled=scheduled, store=store)


def _trigger(app) -> dict:
    headers = {AUTHORIZATION_ENVIRON_KEY: f"Bearer {TEST_SCHEDULER_SECRET}"}
    status, payload = _call(app, SCHEDULED_PATH, method="POST", **headers)
    assert status == "200 OK"
    return payload


def _last_run(store: InMemoryEvidenceStore, minutes_ago: float) -> datetime:
    when = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    StoreSelfEvidenceLog(store=store).record(sweep_size=1, blind=0, when=when)
    return when


def test_the_window_is_three_scheduler_intervals_not_thirty_hours():
    assert SCHEDULER_INTERVAL_SECONDS == 900
    assert WINDOW_SECONDS == 3 * SCHEDULER_INTERVAL_SECONDS


def test_the_board_reports_a_just_run_self_check_as_live():
    store = InMemoryEvidenceStore()
    app = _service(store)
    _trigger(app)

    _status, board = _call(app)

    field = board["self_check"]
    assert set(field) == CONTRACT_KEYS
    assert field["surface"] == "self:sweep"
    assert field["liveness"] == "live"
    assert 0 <= field["age_seconds"] < 60
    assert field["window_seconds"] == WINDOW_SECONDS
    assert field["interval_seconds"] == SCHEDULER_INTERVAL_SECONDS


def test_a_scheduler_that_stopped_an_hour_ago_reads_stale_with_its_age():
    store = InMemoryEvidenceStore()
    last = _last_run(store, minutes_ago=60)

    _status, board = _call(_service(store))

    field = board["self_check"]
    assert field["liveness"] == "stale"
    assert field["last_run_at"] == last.isoformat()
    assert 3590 <= field["age_seconds"] <= 3660


def test_a_self_check_that_never_ran_reads_no_evidence_with_null_age():
    _status, board = _call(_service(InMemoryEvidenceStore()))

    field = board["self_check"]
    assert field["liveness"] == "no_evidence"
    assert field["last_run_at"] is None
    assert field["age_seconds"] is None


def test_the_scheduled_endpoint_itself_judges_an_hour_gap_as_stale():
    """C3: the 30-hour window read a scheduler dead for a day as LIVE."""
    store = InMemoryEvidenceStore()
    _last_run(store, minutes_ago=60)

    payload = _trigger(_service(store))

    assert payload["liveness_before"] == "stale"


class _UnreadableSelfCheckStore(InMemoryEvidenceStore):
    """A store whose read of ``self:sweep`` fails, as a Firestore hiccup would."""

    def latest(self, surface: str):
        if surface == "self:sweep":
            raise ConnectionError("store unavailable")
        return super().latest(surface)


def test_an_unreadable_self_check_record_reads_no_evidence_and_the_board_still_serves():
    status, board = _call(_service(_UnreadableSelfCheckStore()))

    assert status == "200 OK"
    assert board["self_check"]["liveness"] == "no_evidence"
    assert board["self_check"]["age_seconds"] is None


def test_a_naive_stored_timestamp_reads_no_evidence_rather_than_taking_the_board_down():
    store = InMemoryEvidenceStore()
    naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    StoreSelfEvidenceLog(store=store).record(sweep_size=1, blind=0, when=naive)

    status, board = _call(_service(store))

    assert status == "200 OK"
    assert board["self_check"]["liveness"] == "no_evidence"
