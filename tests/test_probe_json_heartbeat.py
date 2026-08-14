"""Locks the generic JSON-heartbeat probe's distinguishing behavior.

Same doctrine as the morning brief probe: the timestamp is read from *inside*
the record (a rewritten mtime must never turn the check green), "never ran"
inside an existing directory is a FAULT, a misconfigured path or a corrupt
record is UNOBSERVABLE, and a stale heartbeat is a FAULT that names its age.
The probe is generic on purpose — any rail that writes a
``{"last_success": ...}`` record (the ops comms-freshness heartbeat contract)
can be declared as a surface in a collector config without new code.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from deadman.evidence.model import Observation
from deadman.probes.json_heartbeat import JsonHeartbeatProbe


def _probe(tmp_path, **kw):
    defaults = dict(
        heartbeat_path=tmp_path / "hb.json",
        surface_id="cron:gcal-sync",
        window_hours=1.0,
    )
    defaults.update(kw)
    return JsonHeartbeatProbe(**defaults)


def _write(path, ts: datetime, **extra) -> None:
    path.write_text(json.dumps({"last_success": ts.isoformat(), **extra}))


def test_missing_file_inside_existing_directory_is_fault(tmp_path) -> None:
    evidence = _probe(tmp_path).observe()
    assert evidence.observation is Observation.FAULT


def test_missing_parent_directory_is_unobservable_not_fault(tmp_path) -> None:
    probe = _probe(tmp_path, heartbeat_path=tmp_path / "no-such-dir" / "hb.json")
    evidence = probe.observe()
    assert evidence.observation is Observation.UNOBSERVABLE


def test_fresh_mtime_with_stale_recorded_timestamp_is_still_fault(tmp_path) -> None:
    hb = tmp_path / "hb.json"
    _write(hb, datetime.now(timezone.utc) - timedelta(hours=9))
    assert (time.time() - hb.stat().st_mtime) < 5  # file itself is brand new

    evidence = _probe(tmp_path).observe()

    assert evidence.observation is Observation.FAULT
    assert "9.0h" in evidence.summary


def test_fresh_heartbeat_is_healthy_and_carries_the_record_as_context(tmp_path) -> None:
    hb = tmp_path / "hb.json"
    _write(
        hb,
        datetime.now(timezone.utc) - timedelta(minutes=5),
        counts={"inserted": 0, "unchanged": 20},
        skipped=[[9, "no Start date"]],
    )

    evidence = _probe(tmp_path).observe()

    assert evidence.observation is Observation.HEALTHY
    assert evidence.surface == "cron:gcal-sync"
    # The run's own counts/skips ride along so downstream interpretation
    # sees what the run did, not just that it happened.
    assert evidence.detail["counts"] == {"inserted": 0, "unchanged": 20}
    assert evidence.detail["skipped"] == [[9, "no Start date"]]


def test_corrupt_json_is_unobservable(tmp_path) -> None:
    (tmp_path / "hb.json").write_text("{not json")
    evidence = _probe(tmp_path).observe()
    assert evidence.observation is Observation.UNOBSERVABLE


def test_missing_timestamp_key_is_unobservable(tmp_path) -> None:
    (tmp_path / "hb.json").write_text(json.dumps({"something_else": 1}))
    evidence = _probe(tmp_path).observe()
    assert evidence.observation is Observation.UNOBSERVABLE


def test_future_dated_heartbeat_is_unobservable_clock_skew(tmp_path) -> None:
    hb = tmp_path / "hb.json"
    _write(hb, datetime.now(timezone.utc) + timedelta(hours=2))
    evidence = _probe(tmp_path).observe()
    assert evidence.observation is Observation.UNOBSERVABLE


def test_bloated_record_extras_are_bounded_not_copied(tmp_path) -> None:
    """A heartbeat written by another process could be huge or hostile; its
    extras must be capped before riding into evidence detail, or an oversized
    detail would blow the ingest body cap and take the sweep's delivery down."""
    hb = tmp_path / "hb.json"
    record = {"last_success": datetime.now(timezone.utc).isoformat()}
    record["huge_string"] = "x" * 100_000
    record["huge_list"] = list(range(10_000))
    for n in range(50):
        record[f"key_{n:02d}"] = n
    hb.write_text(json.dumps(record))

    evidence = _probe(tmp_path).observe()

    assert evidence.observation is Observation.HEALTHY
    assert len(evidence.detail["huge_string"]) <= 300
    assert evidence.detail["huge_list"] == "<list, 10000 items>"
    # 10 extras max, plus the probe's own 3 fields
    assert len(evidence.detail) <= 13
    assert len(json.dumps(evidence.detail)) < 5000
