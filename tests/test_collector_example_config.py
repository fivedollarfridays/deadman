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

INFRA = Path(__file__).resolve().parents[1] / "infra" / "collector"
EXAMPLE_CONFIG = INFRA / "collector.example.json"
RIG_EXAMPLE_CONFIG = INFRA / "collector-rig.example.json"


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
    assert probes[0].host == "mac"
    assert probes[0].surface == "host:mac/disk"


def test_the_rig_example_config_loads_and_builds_a_disk_probe_only():
    """The rig has no morning-brief log, and reuses the disk probe type with
    no new probe code — see 'Real surfaces' in docs/surfaces.md."""
    config = load_config(RIG_EXAMPLE_CONFIG)

    assert config.collector_id == "kevin-rig"
    (probe,) = build_probes(config.probes)

    assert isinstance(probe, DiskProbe)
    assert probe.host == "rig"
    assert probe.surface == "host:rig/disk"


def test_the_mac_and_rig_disk_surfaces_are_distinct():
    mac_probe = build_probes(load_config(EXAMPLE_CONFIG).probes)[0]
    (rig_probe,) = build_probes(load_config(RIG_EXAMPLE_CONFIG).probes)

    assert mac_probe.surface != rig_probe.surface
