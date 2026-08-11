"""``infra/collector/collector.example.json`` is executed, not just written.

The README tells Kevin to copy this file and edit two paths. A doc that
looks plausible and does not actually parse is worse than no doc — the same
lesson `infra/README.md`'s curl runbook already paid for in DM2.2. This test
is what keeps it honest as the config schema evolves.
"""

from __future__ import annotations

from pathlib import Path

from deadman.collector.config import build_probes, load_config
from deadman.probes.disk import DiskProbe
from deadman.probes.morning_brief import MorningBriefProbe

EXAMPLE_CONFIG = (
    Path(__file__).resolve().parents[1] / "infra" / "collector" / "collector.example.json"
)


def test_the_example_config_loads():
    config = load_config(EXAMPLE_CONFIG)

    assert config.collector_id
    assert config.ingest_url.startswith("https://")
    assert len(config.probes) == 2


def test_the_example_config_builds_real_probes():
    config = load_config(EXAMPLE_CONFIG)

    probes = build_probes(config.probes)

    assert isinstance(probes[0], DiskProbe)
    assert isinstance(probes[1], MorningBriefProbe)
