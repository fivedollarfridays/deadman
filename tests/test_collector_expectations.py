"""What a collector is expected to do, declared rather than guessed.

The rule these tests exist to hold: **expected cadence is configuration, not
an observation.** An implementation that learns a collector's interval from
the gaps it has actually seen is one that a slowly dying collector can teach
to expect silence, and the teaching is invisible — the board stays green the
whole way down. So the deadline is a pure function of declared fields, and
``test_the_deadline_is_a_pure_function_of_declared_fields`` fails on any edit
that lets a stored row influence it.

The other half is refusing a config that cannot express the question. A
collector with no declared surfaces, two collectors claiming the same id, or
two collectors claiming the same surface all produce a monitor whose silence
means nothing in particular, so each is a startup failure naming the offending
key rather than a quiet degradation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deadman.collector.config import build_probes, parse_config
from deadman.verify.expectations import (
    DEFAULT_GRACE_INTERVALS,
    CollectorExpectation,
    ExpectationError,
    load_expectations,
    parse_expectations,
)

VALID: dict[str, object] = {
    "collectors": [
        {
            "collector_id": "kevin-mac",
            "interval_seconds": 900,
            "surfaces": ["host:disk/", "cron:morning-brief"],
        }
    ]
}


def _with_collector(**overrides: object) -> dict[str, object]:
    """The valid config with its single collector entry edited."""
    entry = dict(VALID["collectors"][0])  # type: ignore[index]
    entry.update(overrides)
    return {"collectors": [entry]}


class TestAValidDeclaration:
    def test_parses_into_an_expectation(self) -> None:
        (expectation,) = parse_expectations(VALID)

        assert expectation.collector_id == "kevin-mac"
        assert expectation.interval_seconds == 900
        assert expectation.surfaces == ("host:disk/", "cron:morning-brief")

    def test_grace_defaults_to_one_whole_missed_run(self) -> None:
        """One late sweep is not an incident; the second consecutive silence
        is. Stated as a default rather than left to every config file."""
        (expectation,) = parse_expectations(VALID)

        assert expectation.grace_intervals == DEFAULT_GRACE_INTERVALS
        assert expectation.silence_after_seconds == 1800

    def test_grace_can_be_declared_per_collector(self) -> None:
        (expectation,) = parse_expectations(_with_collector(grace_intervals=0.5))

        assert expectation.silence_after_seconds == 1350

    def test_loads_from_a_file(self, tmp_path: Path) -> None:
        path = tmp_path / "collectors.json"
        path.write_text(json.dumps(VALID))

        (expectation,) = load_expectations(path)

        assert expectation.collector_id == "kevin-mac"


class TestTheDeadlineIsDeclaredNotObserved:
    def test_the_deadline_is_a_pure_function_of_declared_fields(self) -> None:
        """The mutation guard for this module's whole reason to exist.

        Two expectations declaring the same cadence have the same deadline,
        whatever either collector has actually been doing. An implementation
        that reached for stored history to compute this could not satisfy it,
        because there is no store here to reach for.
        """
        first = CollectorExpectation("a", interval_seconds=60, surfaces=("s:one",))
        second = CollectorExpectation("b", interval_seconds=60, surfaces=("s:two",))

        assert first.silence_after_seconds == second.silence_after_seconds

    def test_the_deadline_grows_with_the_declared_interval_only(self) -> None:
        slow = CollectorExpectation("a", interval_seconds=3600, surfaces=("s:one",))
        fast = CollectorExpectation("a", interval_seconds=60, surfaces=("s:one",))

        assert slow.silence_after_seconds > fast.silence_after_seconds


class TestAConfigThatCannotExpressTheQuestion:
    def test_rejects_a_payload_that_is_not_an_object(self) -> None:
        with pytest.raises(ExpectationError, match="object"):
            parse_expectations([])

    def test_rejects_a_missing_collectors_key(self) -> None:
        with pytest.raises(ExpectationError, match="collectors"):
            parse_expectations({})

    def test_rejects_an_empty_collector_list(self) -> None:
        """Declaring no collectors is declaring that no silence is noticeable,
        which is the state this whole module exists to make impossible."""
        with pytest.raises(ExpectationError, match="non-empty"):
            parse_expectations({"collectors": []})

    def test_rejects_an_entry_that_is_not_an_object(self) -> None:
        with pytest.raises(ExpectationError, match=r"collectors\[0\]"):
            parse_expectations({"collectors": ["kevin-mac"]})

    @pytest.mark.parametrize("value", ["", "   ", 7, None])
    def test_rejects_a_blank_or_non_string_collector_id(self, value: object) -> None:
        with pytest.raises(ExpectationError, match="collector_id"):
            parse_expectations(_with_collector(collector_id=value))

    def test_rejects_a_missing_interval(self) -> None:
        entry = {k: v for k, v in VALID["collectors"][0].items() if k != "interval_seconds"}  # type: ignore[index]
        with pytest.raises(ExpectationError, match="interval_seconds"):
            parse_expectations({"collectors": [entry]})

    @pytest.mark.parametrize("value", [0, -1, "900", None, True])
    def test_rejects_an_interval_that_is_not_a_positive_number(self, value: object) -> None:
        """Zero or negative is a deadline no collector can ever meet, and a
        bool is a config typo that Python's numeric tower would otherwise
        accept as ``1``."""
        with pytest.raises(ExpectationError, match="interval_seconds"):
            parse_expectations(_with_collector(interval_seconds=value))

    @pytest.mark.parametrize("value", [[], "host:disk/", None, [""], ["ok", 3]])
    def test_rejects_surfaces_that_are_not_a_non_empty_list_of_names(self, value: object) -> None:
        """A collector declaring no surfaces has nothing whose silence could
        be noticed."""
        with pytest.raises(ExpectationError, match="surfaces"):
            parse_expectations(_with_collector(surfaces=value))

    @pytest.mark.parametrize("value", [-0.5, "1", None])
    def test_rejects_a_negative_or_non_numeric_grace(self, value: object) -> None:
        with pytest.raises(ExpectationError, match="grace_intervals"):
            parse_expectations(_with_collector(grace_intervals=value))

    def test_rejects_two_collectors_with_the_same_id(self) -> None:
        """Two entries for one id give the board two contradictory verdicts
        about the same collector, and nothing decides which wins."""
        with pytest.raises(ExpectationError, match="kevin-mac"):
            parse_expectations({"collectors": [VALID["collectors"][0]] * 2})  # type: ignore[index]

    def test_rejects_one_surface_declared_by_two_collectors(self) -> None:
        """Same reason: one surface, two cadences, two derived rows."""
        payload = {
            "collectors": [
                {"collector_id": "a", "interval_seconds": 60, "surfaces": ["cron:morning-brief"]},
                {"collector_id": "b", "interval_seconds": 90, "surfaces": ["cron:morning-brief"]},
            ]
        }

        with pytest.raises(ExpectationError, match="cron:morning-brief"):
            parse_expectations(payload)


class TestAFileThatCannotBeRead:
    def test_a_missing_file_names_the_path(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.json"

        with pytest.raises(ExpectationError, match="nope.json"):
            load_expectations(missing)

    def test_invalid_json_names_the_path(self, tmp_path: Path) -> None:
        path = tmp_path / "collectors.json"
        path.write_text("{not json")

        with pytest.raises(ExpectationError, match="collectors.json"):
            load_expectations(path)


class TestTheShippedExampleIsRunnable:
    def test_the_committed_example_config_parses(self) -> None:
        """The example is documentation that a test keeps honest — an example
        nobody can run is worse than none, because it looks like one."""
        root = Path(__file__).resolve().parents[1]
        example = root / "infra" / "collector" / "collectors.example.json"

        expectations = load_expectations(example)

        assert [e.collector_id for e in expectations] == ["kevin-mac"]

    def test_the_example_declares_the_surfaces_the_example_collector_sweeps(self) -> None:
        """The two example files are one deployment described twice, and a
        surface declared on one side but not swept on the other is a silence
        nobody would notice — precisely this module's failure mode."""
        infra = Path(__file__).resolve().parents[1] / "infra" / "collector"
        collector = json.loads((infra / "collector.example.json").read_text())
        (expectation,) = load_expectations(infra / "collectors.example.json")

        swept = {probe.surface for probe in build_probes(parse_config(collector).probes)}

        assert set(expectation.surfaces) == swept
        assert expectation.collector_id == collector["collector_id"]
