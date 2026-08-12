"""The committed real-world capture is what it claims to be.

Not a parser test — ``deadman.probes.morning_brief`` is already covered by
``tests/test_morning_brief_probe.py`` against synthetic logs. This locks the
one property that makes ``tests/fixtures/real-morning-brief-fault.json``
worth committing at all: it is a real ``FAULT``, not an authored placeholder
that happens to look like one. See ``tests/fixtures/README.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE = FIXTURES / "real-morning-brief-fault.json"
BOARD = FIXTURES / "real-board-capture.json"


def test_the_captured_fixture_is_marked_as_real_and_current():
    payload = json.loads(FIXTURE.read_text())

    assert payload["captured"] is True
    assert payload["evidence"]["surface"] == "cron:morning-brief"


def test_the_captured_fixture_is_a_real_fault_not_a_healthy_placeholder():
    """The whole reason this fixture exists: the acceptance test for DM2.5 is
    not synthetic. A committed 'HEALTHY' row here would mean the capture
    happened after someone fixed morning_brief_send.py, at which point this
    fixture stops being evidence of anything and must be recaptured or
    retired, not quietly reused."""
    payload = json.loads(FIXTURE.read_text())
    evidence = payload["evidence"]

    assert evidence["observation"] == "fault"
    assert evidence["method"] == "local_artifact"
    assert evidence["detail"]["age_hours"] > evidence["detail"]["window_hours"]


def _board_rows(surface: str) -> list[dict]:
    board = json.loads(BOARD.read_text())["board"]
    return [row for row in board["surfaces"] if row["surface"] == surface]


def test_the_board_capture_is_the_deployed_service_not_a_local_run():
    """``docs/PROOF.md``'s second half rests on this having come off the public
    URL. A board generated locally would prove the code works and nothing about
    whether the estate is actually being watched."""
    payload = json.loads(BOARD.read_text())

    assert payload["captured"] is True
    assert payload["url"] == "https://deadman-mrapac5nda-uc.a.run.app/"
    assert payload["http_status"] == 200


def test_the_captured_board_carries_the_outage_as_a_relayed_claim():
    """The wire, visible in output: the collector read the log, so the service
    holds a *report* and says ``reported`` rather than claiming it read a disk
    it cannot reach."""
    (fault,) = [row for row in _board_rows("cron:morning-brief") if row["observation"] == "fault"]

    assert fault["method"] == "reported"
    assert fault["detail"]["age_hours"] > fault["detail"]["window_hours"]
    for withheld in ("collector_id", "received_at", "reported_method", "wire_row_id"):
        assert withheld in fault["detail"]["withheld"]


def test_the_captured_board_keeps_blindness_out_of_the_healthy_count():
    """The same surface is UNOBSERVABLE from Cloud Run, which has no such log.
    Both rows are correct, and the blind one is counted separately — the whole
    argument of the case study, asserted against the capture it is written
    from."""
    board = json.loads(BOARD.read_text())["board"]
    rows = _board_rows("cron:morning-brief")
    blind = [row for row in rows if row["observation"] == "unobservable"]

    assert blind, "the service's own copy of the surface must appear, blind rather than absent"
    assert "cron:morning-brief" in board["blind_spots"]
    assert board["healthy_count"] + board["fault_count"] + board["blind_count"] == len(
        board["surfaces"]
    )


def test_the_captured_board_proves_the_collector_was_alive_when_it_spoke():
    """A FAULT relayed by a collector nobody was watching is worth much less.
    ``collector:kevin-mac`` is on the same board, live inside its deadline."""
    (collector,) = _board_rows("collector:kevin-mac")

    assert collector["observation"] == "healthy"
    assert collector["detail"]["cadence_seconds"] == 900.0
    assert collector["detail"]["silent_after_seconds"] == 1800.0
    assert collector["detail"]["silent_for_seconds"] < collector["detail"]["silent_after_seconds"]
