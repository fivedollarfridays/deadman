"""Locks the series-row probe's distinguishing behavior.

The artifact this reads is a daily series — ``[{"date": ..., "count": ...}]``
— written by a tracker whose correct failure mode is writing NO row at all
(unknown-never-zero). That is precisely why ``json_heartbeat`` cannot read
it: absence of a row is the signal, and there is no ``last_success`` field
to age.

The timezone case is not decorative. Rows are stamped in local calendar days
(America/Chicago for this estate). A probe reading "today" in UTC starts
asking for tomorrow's row at 7pm local and would false-alarm every single
evening — an alarm that fires nightly is an alarm that gets muted, which is
the failure this project exists to prevent.
"""

from __future__ import annotations

import json

from deadman.evidence.model import Observation
from deadman.probes.base import run_probe
from deadman.probes.series_row import SeriesRowProbe

TZ = "America/Chicago"


def _probe(tmp_path, **kw):
    defaults = dict(
        series_path=tmp_path / "devpost-series.json",
        surface_id="cron:devpost",
        timezone_name=TZ,
    )
    defaults.update(kw)
    return SeriesRowProbe(**defaults)


def _write(tmp_path, rows, name="devpost-series.json"):
    (tmp_path / name).write_text(json.dumps(rows))


def test_row_for_today_is_healthy_and_carries_the_payload(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(TZ)).date().isoformat()
    _write(tmp_path, [{"date": "2026-01-01", "count": 3}, {"date": today, "count": 14}])
    ev = _probe(tmp_path).observe()
    assert ev.observation is Observation.HEALTHY
    assert ev.detail["count"] == 14
    assert today in ev.summary


def test_no_row_for_today_is_a_fault(tmp_path):
    """The tracker did not run. That is evidence about the surface."""
    _write(tmp_path, [{"date": "2026-01-01", "count": 3}])
    ev = _probe(tmp_path).observe()
    assert ev.observation is Observation.FAULT
    assert "no row" in ev.summary.lower() or "did not" in ev.summary.lower()


def test_empty_series_inside_existing_dir_is_a_fault(tmp_path):
    _write(tmp_path, [])
    assert _probe(tmp_path).observe().observation is Observation.FAULT


def test_missing_file_inside_existing_dir_is_a_fault(tmp_path):
    """Never written, but the directory is ours and present: a real finding."""
    assert _probe(tmp_path).observe().observation is Observation.FAULT


def test_missing_directory_is_unobservable(tmp_path):
    """Our own bad path is our problem, not the tracker's."""
    ev = _probe(tmp_path, series_path=tmp_path / "nope" / "s.json").observe()
    assert ev.observation is Observation.UNOBSERVABLE


def test_unparseable_series_is_unobservable(tmp_path):
    (tmp_path / "devpost-series.json").write_text("{not json")
    assert _probe(tmp_path).observe().observation is Observation.UNOBSERVABLE


def test_object_instead_of_list_is_unobservable(tmp_path):
    _write(tmp_path, {"date": "2026-08-20"})
    assert _probe(tmp_path).observe().observation is Observation.UNOBSERVABLE


def test_local_calendar_day_not_utc(tmp_path):
    """Late local evening is already tomorrow in UTC. The row stamped for the
    LOCAL day must still read healthy, or this alarms nightly."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    local_today = datetime.now(ZoneInfo(TZ)).date().isoformat()
    utc_today = datetime.now(ZoneInfo("UTC")).date().isoformat()
    _write(tmp_path, [{"date": local_today, "count": 1}])
    assert _probe(tmp_path).observe().observation is Observation.HEALTHY
    if local_today != utc_today:  # only meaningful across the boundary
        _write(tmp_path, [{"date": utc_today, "count": 1}])
        assert _probe(tmp_path).observe().observation is Observation.FAULT


def test_extras_are_bounded(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(TZ)).date().isoformat()
    row = {"date": today, "blob": "x" * 5000}
    row.update({f"k{i}": i for i in range(50)})
    _write(tmp_path, [row])
    ev = _probe(tmp_path).observe()
    assert len(ev.detail) <= 12
    assert all(not isinstance(v, str) or len(v) <= 400 for v in ev.detail.values())


def test_never_raises(tmp_path):
    """The containment contract: an exception escaping a probe must become an
    explicit blind state, never take the sweep down. Forced with a path whose
    very existence check explodes."""

    class _HostilePath:
        name = "boom.json"
        parent = tmp_path

        def exists(self):
            raise RuntimeError("filesystem exploded in an unexpected way")

    ev = run_probe(_probe(tmp_path, series_path=_HostilePath()))  # type: ignore[arg-type]
    assert ev.observation is Observation.UNOBSERVABLE
