"""Which probes a collector runs is a fact about a config file, not the code.

The failure this guards against is the opposite of DM1's problem: a collector
that only knows the surfaces someone remembered to compile in. Every case
here either proves a valid config builds the real probe classes with the
right arguments, or proves a bad config fails loudly and names the exact key
that is wrong — "sweeps nothing, silently" is the one outcome every test
below refuses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deadman.collector.config import (
    DEFAULT_SPOOL_DIR,
    CollectorConfig,
    ConfigError,
    ProbeSpec,
    build_probes,
    load_config,
    parse_config,
)
from deadman.probes.disk import DiskProbe
from deadman.probes.morning_brief import MorningBriefProbe

VALID_PAYLOAD = {
    "collector_id": "kevin-mac",
    "ingest_url": "https://deadman.example.com/",
    "probes": [
        {"type": "disk", "args": {"volume": "/", "history_path": "/tmp/deadman/disk.jsonl"}},
        {"type": "morning_brief", "args": {"log_path": "/tmp/deadman/brief.jsonl"}},
    ],
}


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "collector.json"
    path.write_text(json.dumps(payload))
    return path


class TestParseConfig:
    def test_a_valid_payload_parses_into_a_collector_config(self):
        config = parse_config(VALID_PAYLOAD)

        assert isinstance(config, CollectorConfig)
        assert config.collector_id == "kevin-mac"
        assert len(config.probes) == 2
        assert config.probes[0] == ProbeSpec(
            type="disk", args={"volume": "/", "history_path": "/tmp/deadman/disk.jsonl"}
        )

    def test_a_trailing_slash_on_the_ingest_url_is_stripped(self):
        config = parse_config(VALID_PAYLOAD)

        assert config.ingest_url == "https://deadman.example.com"

    def test_spool_dir_defaults_when_absent(self):
        config = parse_config(VALID_PAYLOAD)

        assert config.spool_dir == DEFAULT_SPOOL_DIR

    def test_spool_dir_is_read_from_the_payload_when_present(self):
        payload = {**VALID_PAYLOAD, "spool_dir": "/custom/spool"}

        config = parse_config(payload)

        assert config.spool_dir == Path("/custom/spool")

    def test_the_payload_must_be_a_json_object(self):
        with pytest.raises(ConfigError, match="JSON object"):
            parse_config(["not", "an", "object"])

    @pytest.mark.parametrize("missing", ["collector_id", "ingest_url", "probes"])
    def test_a_missing_required_key_names_itself(self, missing):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != missing}

        with pytest.raises(ConfigError, match=missing):
            parse_config(payload)

    def test_an_empty_collector_id_is_refused(self):
        payload = {**VALID_PAYLOAD, "collector_id": "   "}

        with pytest.raises(ConfigError, match="collector_id"):
            parse_config(payload)

    def test_probes_must_be_a_non_empty_list(self):
        payload = {**VALID_PAYLOAD, "probes": []}

        with pytest.raises(ConfigError, match="probes"):
            parse_config(payload)

    def test_a_probe_entry_that_is_not_an_object_names_its_index(self):
        payload = {**VALID_PAYLOAD, "probes": ["not-an-object"]}

        with pytest.raises(ConfigError, match=r"probes\[0\]"):
            parse_config(payload)

    def test_a_probe_entry_missing_a_type_names_its_index(self):
        payload = {**VALID_PAYLOAD, "probes": [{"args": {}}]}

        with pytest.raises(ConfigError, match=r"probes\[0\]\.type"):
            parse_config(payload)

    def test_probe_args_default_to_empty(self):
        payload = {**VALID_PAYLOAD, "probes": [{"type": "morning_brief", "args": {}}]}

        config = parse_config(payload)

        assert config.probes[0].args == {}

    def test_probe_args_must_be_an_object(self):
        payload = {**VALID_PAYLOAD, "probes": [{"type": "disk", "args": ["nope"]}]}

        with pytest.raises(ConfigError, match=r"probes\[0\]\.args"):
            parse_config(payload)


class TestLoadConfig:
    def test_loads_and_parses_a_real_file(self, tmp_path):
        path = _write(tmp_path, VALID_PAYLOAD)

        config = load_config(path)

        assert config.collector_id == "kevin-mac"

    def test_a_missing_file_fails_loudly_naming_the_path(self, tmp_path):
        path = tmp_path / "does-not-exist.json"

        with pytest.raises(ConfigError, match=str(path)):
            load_config(path)

    def test_malformed_json_fails_loudly(self, tmp_path):
        path = tmp_path / "collector.json"
        path.write_text("{not json")

        with pytest.raises(ConfigError, match="JSON"):
            load_config(path)


class TestBuildProbes:
    def test_builds_the_real_probe_classes(self):
        config = parse_config(VALID_PAYLOAD)

        probes = build_probes(config.probes)

        assert isinstance(probes[0], DiskProbe)
        assert isinstance(probes[1], MorningBriefProbe)

    def test_string_path_arguments_become_path_objects(self):
        config = parse_config(VALID_PAYLOAD)

        probes = build_probes(config.probes)

        disk_probe = probes[0]
        assert isinstance(disk_probe.history_path, Path)
        assert isinstance(disk_probe.volume, Path)

    def test_an_unknown_probe_type_names_itself(self):
        specs = (ProbeSpec(type="not-a-real-probe", args={}),)

        with pytest.raises(ConfigError, match="not-a-real-probe"):
            build_probes(specs)

    def test_args_that_do_not_match_the_probes_constructor_fail_loudly(self):
        specs = (ProbeSpec(type="disk", args={"nonexistent_kwarg": 1}),)

        with pytest.raises(ConfigError, match="disk"):
            build_probes(specs)

    def test_non_path_arguments_pass_through_untouched(self):
        specs = (ProbeSpec(type="disk", args={"runway_days": 7.0}),)

        (probe,) = build_probes(specs)

        assert probe.runway_days == 7.0
