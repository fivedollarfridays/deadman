"""DM3.1 — a producer's heartbeat keys must never crash the probe reading them.

Found live, from the alert path working. ``cron:devpost`` alerted five times on
2026-08-27 with::

    probe raised TypeError: JsonHeartbeatProbe._fault()
    got multiple values for argument 'source'

``_fault(self, summary, source, **detail)`` takes ``source`` positionally, and
both call sites also splat ``**detail`` — which ``_bounded_extras`` fills with
arbitrary keys copied straight out of the heartbeat JSON. Its ``exclude`` is a
single string (the timestamp key), so ``last_success`` is protected and nothing
else is. The real devpost heartbeat is ``{last_success, row, source}``.

**The bug inverts the diagnosis exactly when the monitor is load-bearing.** The
probe was reporting a real staleness and raised on the way, so the board showed
UNOBSERVABLE ("we cannot see it — our problem") for something that was FAULT
("the thing is broken — theirs"). The healthy path never touches ``**detail``,
so this is invisible until a surface actually fails.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone

import pytest

from deadman.evidence.model import Evidence, Observation
from deadman.probes.json_heartbeat import JsonHeartbeatProbe

RESERVED = [f.name for f in dataclasses.fields(Evidence) if f.name != "read_at"]


def _probe(tmp_path, **kw):
    defaults = dict(
        heartbeat_path=tmp_path / "hb.json",
        surface_id="cron:devpost",
        window_hours=1.0,
    )
    defaults.update(kw)
    return JsonHeartbeatProbe(**defaults)


def _stale(path, **extra) -> None:
    """A heartbeat old enough to force the FAULT path — the only path that
    splats ``**detail``, and therefore the only one that can collide."""
    ts = datetime.now(timezone.utc) - timedelta(hours=9)
    path.write_text(json.dumps({"last_success": ts.isoformat(), **extra}))


@pytest.mark.parametrize("key", RESERVED)
def test_reserved_key_in_heartbeat_does_not_crash_the_probe(tmp_path, key) -> None:
    """Table-driven over every Evidence field, not just the one that bit us.
    ``source`` is what devpost carried; the next producer could carry any."""
    _stale(tmp_path / "hb.json", **{key: "producer-supplied value"})
    evidence = _probe(tmp_path).observe()
    assert evidence.observation is Observation.FAULT


def test_devpost_real_payload_reports_fault(tmp_path) -> None:
    """The actual shape from ops data/devpost-heartbeat.json — a real fixture,
    because a synthetic one is what let this ship."""
    _stale(
        tmp_path / "hb.json",
        row={"date": "2026-08-25", "count": 18},
        source="/Users/kevinmasterson/prod/kai-studio/ops/data/devpost-series.json",
    )
    evidence = _probe(tmp_path).observe()
    assert evidence.observation is Observation.FAULT
    assert "9." in evidence.summary  # names its age, per the probe's contract


def test_colliding_key_is_preserved_not_silently_dropped(tmp_path) -> None:
    """Doctrine §5: tolerate drift or fail loud — never silently drop. The
    producer's value must still be visible somewhere in the evidence detail."""
    _stale(tmp_path / "hb.json", source="/path/the/producer/cared/about")
    detail = _probe(tmp_path).observe().detail
    rendered = json.dumps(detail)
    assert "/path/the/producer/cared/about" in rendered


def test_probe_source_still_reports_the_heartbeat_path(tmp_path) -> None:
    """The collision must be resolved in the producer's favour losing, not the
    probe's: Evidence.source stays the artifact the probe actually read."""
    hb = tmp_path / "hb.json"
    _stale(hb, source="not-the-real-source")
    assert _probe(tmp_path).observe().source == str(hb)


def test_healthy_path_unchanged_by_reserved_keys(tmp_path) -> None:
    """The healthy branch never splatted detail, so it was never broken. Prove
    the fix did not change it."""
    ts = datetime.now(timezone.utc) - timedelta(minutes=1)
    (tmp_path / "hb.json").write_text(
        json.dumps({"last_success": ts.isoformat(), "source": "x", "brand": "door"})
    )
    evidence = _probe(tmp_path).observe()
    assert evidence.observation is Observation.HEALTHY
    assert evidence.source == str(tmp_path / "hb.json")
