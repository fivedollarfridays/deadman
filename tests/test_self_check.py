"""Self-liveness: can deadman prove it ran, from evidence it wrote itself.

The failure being designed against is specific. A sibling system ran dead for
nine days behind a green heartbeat, and nobody noticed because the thing that
died was also the thing that would have reported the death. A monitor that
cannot establish its own liveness is not a monitor, it is a hope.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from deadman.self_check import Liveness, SelfEvidenceLog, self_check


def _at(path, *, ago_hours: float, sweep_size: int = 2, blind: int = 1) -> None:
    """Write one self-evidence row dated ``ago_hours`` in the past."""
    log = SelfEvidenceLog(path=path)
    log.record(
        sweep_size=sweep_size,
        blind=blind,
        when=datetime.now(timezone.utc) - timedelta(hours=ago_hours),
    )


def test_record_then_latest_round_trips_the_timestamp(tmp_path):
    log = SelfEvidenceLog(path=tmp_path / "self.jsonl")
    when = datetime(2026, 8, 10, 9, 30, tzinfo=timezone.utc)

    log.record(sweep_size=4, blind=1, when=when)

    assert log.latest() == when


def test_latest_is_none_when_nothing_was_ever_written(tmp_path):
    log = SelfEvidenceLog(path=tmp_path / "self.jsonl")

    assert log.latest() is None


def test_recent_sweep_is_live_and_exits_zero(tmp_path):
    path = tmp_path / "self.jsonl"
    _at(path, ago_hours=1)

    result = self_check(SelfEvidenceLog(path=path), window_hours=30)

    assert result.liveness is Liveness.LIVE
    assert result.exit_code == 0


def test_sweep_older_than_the_window_is_stale_and_exits_non_zero(tmp_path):
    path = tmp_path / "self.jsonl"
    _at(path, ago_hours=49)

    result = self_check(SelfEvidenceLog(path=path), window_hours=30)

    assert result.liveness is Liveness.STALE
    assert result.exit_code != 0
    assert "49" in result.summary


def test_no_evidence_at_all_exits_non_zero(tmp_path):
    result = self_check(SelfEvidenceLog(path=tmp_path / "never-written.jsonl"), window_hours=30)

    assert result.liveness is Liveness.NO_EVIDENCE
    assert result.exit_code != 0


def test_an_empty_log_is_no_evidence_not_live(tmp_path):
    # A file that exists but holds nothing is the shape left behind by a run
    # that opened its log and died. It has never proved a sweep.
    path = tmp_path / "self.jsonl"
    path.write_text("")

    result = self_check(SelfEvidenceLog(path=path), window_hours=30)

    assert result.liveness is Liveness.NO_EVIDENCE
    assert result.exit_code != 0


def test_a_fresh_mtime_does_not_make_stale_content_live(tmp_path):
    # The exact bug that let a sibling system's freshness check go green with
    # nothing regenerated: a checkout, rsync or restore rewrites mtime while
    # the contents stay weeks old. The timestamp must come from inside the row.
    path = tmp_path / "self.jsonl"
    _at(path, ago_hours=200)
    os.utime(path, None)  # touch: mtime is now, content is 200h old

    result = self_check(SelfEvidenceLog(path=path), window_hours=30)

    assert result.liveness is Liveness.STALE
    assert result.exit_code != 0


def test_a_completed_sweep_records_its_own_evidence(tmp_path):
    # Without this wiring the log is never written in production and
    # self_check answers NO_EVIDENCE forever, which is a self-check that
    # checks nothing.
    from deadman.probes.disk import DiskProbe
    from deadman.service import build_board

    path = tmp_path / "self.jsonl"
    build_board(
        [DiskProbe(history_path=tmp_path / "disk.jsonl")],
        self_log=SelfEvidenceLog(path=path),
    )

    assert self_check(SelfEvidenceLog(path=path), window_hours=30).liveness is Liveness.LIVE


def test_the_recorded_row_carries_what_the_sweep_saw(tmp_path):
    from deadman.probes.disk import DiskProbe
    from deadman.probes.morning_brief import MorningBriefProbe
    from deadman.service import build_board

    path = tmp_path / "self.jsonl"
    build_board(
        [
            DiskProbe(history_path=tmp_path / "disk.jsonl"),
            MorningBriefProbe(log_path=tmp_path / "nope" / "missing.jsonl"),
        ],
        self_log=SelfEvidenceLog(path=path),
    )

    row = json.loads(path.read_text().splitlines()[-1])
    assert row["sweep_size"] == 2
    assert row["blind"] == 1


def test_serving_a_request_records_self_evidence(tmp_path):
    # The deployed service is the thing whose liveness must be provable, so
    # the wiring has to reach the WSGI app, not stop at build_board.
    from deadman.probes.disk import DiskProbe
    from deadman.service import make_app

    path = tmp_path / "self.jsonl"
    app = make_app(
        lambda: [DiskProbe(history_path=tmp_path / "disk.jsonl")],
        self_log=SelfEvidenceLog(path=path),
    )
    list(app({"REQUEST_METHOD": "GET"}, lambda *_: None))

    assert self_check(SelfEvidenceLog(path=path), window_hours=30).liveness is Liveness.LIVE


def test_a_rejected_request_records_nothing(tmp_path):
    # A 405 is not a sweep. Recording it would let a stream of bad requests
    # forge liveness for a service whose probes never ran.
    from deadman.probes.disk import DiskProbe
    from deadman.service import make_app

    path = tmp_path / "self.jsonl"
    app = make_app(
        lambda: [DiskProbe(history_path=tmp_path / "disk.jsonl")],
        self_log=SelfEvidenceLog(path=path),
    )
    list(app({"REQUEST_METHOD": "POST"}, lambda *_: None))

    assert self_check(SelfEvidenceLog(path=path), window_hours=30).liveness is Liveness.NO_EVIDENCE


def test_a_torn_final_row_does_not_blind_the_check(tmp_path):
    # A crashed write leaves a half-line. One bad row must not hide a perfectly
    # good sweep recorded moments earlier.
    path = tmp_path / "self.jsonl"
    _at(path, ago_hours=1)
    with path.open("a") as fh:
        fh.write('{"ts": "2026-08-1')

    result = self_check(SelfEvidenceLog(path=path), window_hours=30)

    assert result.liveness is Liveness.LIVE
