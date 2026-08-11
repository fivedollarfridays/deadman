"""Locks the morning brief probe's distinguishing behavior.

The whole point of this probe is that it reads the timestamp *inside* the
last row rather than trusting the log file's mtime, and that it tells
"nothing to see" (UNOBSERVABLE) apart from "saw it and it's broken" (FAULT).
These tests target exactly those distinctions rather than the happy path.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from deadman.evidence.model import Observation
from deadman.probes.morning_brief import MorningBriefProbe


def _row(ts: datetime) -> str:
    return json.dumps({"ts": ts.isoformat()}) + "\n"


def test_missing_log_inside_existing_directory_is_fault(tmp_path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    probe = MorningBriefProbe(log_path=log_dir / "brief.log")

    evidence = probe.observe()

    assert evidence.observation is Observation.FAULT


def test_missing_parent_directory_is_unobservable_not_fault(tmp_path) -> None:
    log_path = tmp_path / "nonexistent" / "brief.log"
    probe = MorningBriefProbe(log_path=log_path)

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.FAULT
    assert evidence.detail["path"] == str(log_path)


def test_fresh_mtime_with_stale_last_row_is_still_fault(tmp_path) -> None:
    log_path = tmp_path / "brief.log"
    stale = datetime.now(timezone.utc) - timedelta(hours=40)
    log_path.write_text(_row(stale))

    # The file was just written, so its mtime is now. The probe must ignore
    # that and rule on the timestamp encoded in the row instead.
    assert (time.time() - log_path.stat().st_mtime) < 5

    probe = MorningBriefProbe(log_path=log_path)
    evidence = probe.observe()

    assert evidence.observation is Observation.FAULT


def test_torn_final_row_falls_back_to_newest_parseable_row(tmp_path) -> None:
    log_path = tmp_path / "brief.log"
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    log_path.write_text(_row(recent) + "{not valid json\n")

    probe = MorningBriefProbe(log_path=log_path)
    evidence = probe.observe()

    assert evidence.observation is Observation.HEALTHY
    assert evidence.detail["last_send_at"] == recent.isoformat()
    assert evidence.detail["row_count"] == 2


def test_future_dated_timestamp_is_unobservable(tmp_path) -> None:
    log_path = tmp_path / "brief.log"
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    log_path.write_text(_row(future))

    probe = MorningBriefProbe(log_path=log_path)
    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
