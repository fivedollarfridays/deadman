"""Locks the disk probe's central claim: rate, not just level.

A healthy level with a bad trend must fault, because that is the exact
failure this probe exists to catch (see module docstring on DiskProbe). The
other tests lock the trend math's edge behavior: no projection from one
sample, and no single outlier flipping the verdict.
"""

from __future__ import annotations

import json
import shutil
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

from deadman.evidence.model import Observation
from deadman.probes.disk import GB, DiskProbe

_Usage = namedtuple("_Usage", ["total", "used", "free"])


def _mock_disk_usage(monkeypatch, free_bytes: int, total_bytes: int = 200 * GB) -> None:
    def fake_disk_usage(_path):
        return _Usage(total=total_bytes, used=total_bytes - free_bytes, free=free_bytes)

    monkeypatch.setattr(shutil, "disk_usage", fake_disk_usage)


def _seed_history(history_path, samples: list[tuple[datetime, int]]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a") as fh:
        for ts, free in samples:
            fh.write(json.dumps({"ts": ts.isoformat(), "free": free}) + "\n")


def test_ample_free_space_with_shrinking_slope_inside_runway_is_fault(
    tmp_path, monkeypatch
) -> None:
    now = datetime.now(timezone.utc)
    history_path = tmp_path / "disk-history.jsonl"
    # A perfectly linear -20GB/day slope: 90GB two days ago, 70GB yesterday,
    # 50GB now. 50GB is well above the 10GB floor, but at -20GB/day it hits
    # the floor in 2 days, inside the 14-day runway window.
    _seed_history(
        history_path,
        [
            (now - timedelta(days=2), 90 * GB),
            (now - timedelta(days=1), 70 * GB),
        ],
    )
    _mock_disk_usage(monkeypatch, free_bytes=50 * GB)

    probe = DiskProbe(history_path=history_path, floor_bytes=10 * GB)
    evidence = probe.observe()

    assert evidence.observation is Observation.FAULT
    assert evidence.detail["free_gb"] == 50.0
    assert evidence.detail["runway_days"] <= probe.runway_days


def test_single_sample_is_healthy_with_no_trend(tmp_path, monkeypatch) -> None:
    history_path = tmp_path / "disk-history.jsonl"
    _mock_disk_usage(monkeypatch, free_bytes=50 * GB)

    probe = DiskProbe(history_path=history_path, floor_bytes=10 * GB)
    evidence = probe.observe()

    assert evidence.observation is Observation.HEALTHY
    assert evidence.detail["samples"] == 1
    assert evidence.detail["trend"] == "insufficient history"
    assert "slope_gb_per_day" not in evidence.detail


def test_no_host_preserves_the_original_surface_id(tmp_path) -> None:
    probe = DiskProbe(history_path=tmp_path / "disk-history.jsonl")

    assert probe.surface == "host:disk/"


def test_host_makes_the_surface_id_distinct_across_machines(tmp_path) -> None:
    mac = DiskProbe(volume=Path("/"), host="mac", history_path=tmp_path / "mac.jsonl")
    rig = DiskProbe(volume=Path("/"), host="rig", history_path=tmp_path / "rig.jsonl")

    assert mac.surface != rig.surface
    assert mac.surface == "host:mac/disk"
    assert rig.surface == "host:rig/disk"


def test_missing_volume_is_unobservable_with_the_path_in_detail(tmp_path, monkeypatch) -> None:
    missing = tmp_path / "does-not-exist"

    def fake_disk_usage(_path):
        raise FileNotFoundError(f"[Errno 2] No such file or directory: '{missing}'")

    monkeypatch.setattr(shutil, "disk_usage", fake_disk_usage)

    probe = DiskProbe(volume=missing, history_path=tmp_path / "disk-history.jsonl")
    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.FAULT
    assert evidence.detail["path"] == str(missing)


def test_one_outlier_sample_does_not_flip_the_projection(tmp_path, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    history_path = tmp_path / "disk-history.jsonl"
    # Stable around 80-83GB across four days, with one mid-series outlier
    # dip to 40GB (a transient temp file). The least-squares slope over the
    # whole series stays flat/positive, so this must NOT fault.
    _seed_history(
        history_path,
        [
            (now - timedelta(days=4), 80 * GB),
            (now - timedelta(days=3), 82 * GB),
            (now - timedelta(days=2), 40 * GB),
            (now - timedelta(days=1), 81 * GB),
        ],
    )
    _mock_disk_usage(monkeypatch, free_bytes=83 * GB)

    probe = DiskProbe(history_path=history_path, floor_bytes=10 * GB)
    evidence = probe.observe()

    assert evidence.observation is Observation.HEALTHY
    assert evidence.detail["slope_gb_per_day"] >= 0
