"""What each collector promised to do, declared in configuration.

**Cadence is declared, never inferred.** This module holds nothing but the
declaration, and it is a separate module from the verdict for exactly that
reason: :mod:`deadman.verify.collector_liveness` is handed an expectation and
a store, and the only place a deadline could come from is the expectation.

The alternative — learning each collector's interval from the gaps it has
actually shown — is seductive because it needs no configuration and adapts to
reality. That is the failure. A collector that dies slowly, running every
fifteen minutes, then every hour, then daily, teaches an inferring monitor to
expect exactly the silence it is producing, and the board stays green the
whole way down. The estate's cadence is a decision somebody made; it is not
something to be discovered from the corpse.

**Silence is called at the cadence plus one whole missed run.** A monitor that
alarms the instant a sweep is a second late is a monitor whose alarms get
filtered, so :data:`DEFAULT_GRACE_INTERVALS` buys one skipped run and no more:
two consecutive silences are an incident. The grace is expressed in intervals
rather than seconds so it stays proportional to whatever cadence a collector
declares, and it is still a declared number, not one derived from history.

**A config that cannot express the question is refused at startup.** A
collector with no surfaces, a duplicate id, or two collectors claiming one
surface each produce a board that either says nothing or says two things.
Every refusal below names the offending key, in the style of
:mod:`deadman.collector.config`, so the fix is one line from the message.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: How much lateness is tolerated before silence becomes a fault, in units of
#: the collector's own declared interval. One means: a single missed run is
#: not yet an incident, two consecutive ones are.
DEFAULT_GRACE_INTERVALS = 1.0


class ExpectationError(ValueError):
    """The collector liveness config is not one this service can verify.

    Always names the specific key or collector at fault. An unverifiable
    config must fail loudly at startup, because the way it fails quietly is by
    watching nobody — and a monitor watching nobody looks exactly like an
    estate with nothing wrong.
    """


@dataclass(frozen=True)
class CollectorExpectation:
    """One collector's declared duty: report these surfaces, this often."""

    collector_id: str
    """Matches the ``collector_id`` a collector signs its batches with, which
    is what :mod:`deadman.ingest.arrival` records on every stored row."""

    interval_seconds: float
    """The declared sweep cadence. Configuration, never an observation."""

    surfaces: tuple[str, ...]
    """Surface ids this collector is responsible for. Required, and non-empty:
    a collector whose surfaces are unknown is one whose silence about any
    particular surface cannot be noticed."""

    grace_intervals: float = DEFAULT_GRACE_INTERVALS

    @property
    def silence_after_seconds(self) -> float:
        """How long a gap may be before it is a fault rather than lateness."""
        return self.interval_seconds * (1.0 + self.grace_intervals)


def load_expectations(path: Path) -> tuple[CollectorExpectation, ...]:
    """Read and validate a declaration file, or raise :class:`ExpectationError`."""
    try:
        raw = path.read_text()
    except OSError as exc:
        raise ExpectationError(f"cannot read collector liveness config {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExpectationError(f"{path} is not valid JSON: {exc}") from exc
    return parse_expectations(payload)


def parse_expectations(payload: Any) -> tuple[CollectorExpectation, ...]:
    """Validate an already-parsed payload into expectations."""
    if not isinstance(payload, Mapping):
        raise ExpectationError("collector liveness config must be a JSON object")
    if "collectors" not in payload:
        raise ExpectationError("config is missing required key 'collectors'")

    entries = payload["collectors"]
    if not isinstance(entries, list) or not entries:
        raise ExpectationError("config key 'collectors' must be a non-empty array")

    expectations = tuple(_parse_one(index, entry) for index, entry in enumerate(entries))
    _refuse_ambiguous_ownership(expectations)
    return expectations


def _parse_one(index: int, entry: Any) -> CollectorExpectation:
    if not isinstance(entry, Mapping):
        raise ExpectationError(f"config key 'collectors[{index}]' must be a JSON object")

    collector_id = entry.get("collector_id")
    if not isinstance(collector_id, str) or not collector_id.strip():
        raise ExpectationError(
            f"config key 'collectors[{index}].collector_id' must be a non-empty string"
        )

    return CollectorExpectation(
        collector_id=collector_id,
        interval_seconds=_interval(index, entry),
        surfaces=_surfaces(index, entry),
        grace_intervals=_grace(index, entry),
    )


def _interval(index: int, entry: Mapping[str, Any]) -> float:
    """A positive number of seconds. Zero or negative is a deadline no
    collector can meet, and a bare ``True`` is a typo Python's numeric tower
    would otherwise silently accept as one second."""
    value = entry.get("interval_seconds")
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ExpectationError(
            f"config key 'collectors[{index}].interval_seconds' must be a positive number "
            f"of seconds, declaring how often this collector is expected to report"
        )
    return float(value)


def _grace(index: int, entry: Mapping[str, Any]) -> float:
    value = entry.get("grace_intervals", DEFAULT_GRACE_INTERVALS)
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ExpectationError(
            f"config key 'collectors[{index}].grace_intervals' must be a non-negative "
            f"number of whole intervals"
        )
    return float(value)


def _surfaces(index: int, entry: Mapping[str, Any]) -> tuple[str, ...]:
    value = entry.get("surfaces")
    if not isinstance(value, list) or not value:
        raise ExpectationError(
            f"config key 'collectors[{index}].surfaces' must be a non-empty array of the "
            f"surface ids this collector reports"
        )
    for position, surface in enumerate(value):
        if not isinstance(surface, str) or not surface.strip():
            raise ExpectationError(
                f"config key 'collectors[{index}].surfaces[{position}]' must be a non-empty string"
            )
    return tuple(value)


def _refuse_ambiguous_ownership(expectations: tuple[CollectorExpectation, ...]) -> None:
    """One id per collector, one collector per surface.

    Both duplicates produce a board that contradicts itself — two verdicts
    about one collector, or two cadences for one surface — with nothing to
    decide which wins. Refusing is the only honest option.
    """
    declared: set[str] = set()
    owner: dict[str, str] = {}
    for expectation in expectations:
        if expectation.collector_id in declared:
            raise ExpectationError(
                f"collector id {expectation.collector_id!r} is declared twice; one entry "
                f"per collector, listing all of its surfaces"
            )
        declared.add(expectation.collector_id)
        for surface in expectation.surfaces:
            if surface in owner:
                raise ExpectationError(
                    f"surface {surface!r} is declared by both {owner[surface]!r} and "
                    f"{expectation.collector_id!r}; a surface has exactly one expected reporter"
                )
            owner[surface] = expectation.collector_id
