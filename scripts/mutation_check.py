#!/usr/bin/env python3
"""Prove each liveness guard is load-bearing by breaking it on purpose.

A test suite that passes proves the code passes its tests. It does not prove
the tests would notice if the code were wrong — and for collector liveness
that distinction is the whole game, because every guard here is the difference
between an alarm and a quiet board, and a guard nothing tests can be deleted
by a future refactor with the suite still green.

So each guard below is inverted in the source, one at a time, and the named
test that exists to catch that inversion is run. The mutation must make that
test *fail*. A mutation the suite survives is reported as a hole, with a
non-zero exit, because it means the guard is currently unprotected.

    PYTHONDONTWRITEBYTECODE=1 python scripts/mutation_check.py

Every edit is written to the real file and restored in a ``finally``, with a
second restore registered at exit so an interrupt cannot leave a mutated
source behind. Nothing here is imported by the package or the suite.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIVENESS = REPO / "src" / "deadman" / "verify" / "collector_liveness.py"
EXPECTATIONS = REPO / "src" / "deadman" / "verify" / "expectations.py"
SUITE = "tests/test_collector_liveness.py"


@dataclass(frozen=True)
class Mutation:
    """One guard, broken one way, and the test that must object."""

    guard: str
    path: Path
    before: str
    after: str
    test: str


MUTATIONS = (
    Mutation(
        guard="silence past the declared deadline is STALE",
        path=LIVENESS,
        before="liveness = Liveness.STALE if silent > expectation.silence_after_seconds",
        after="liveness = Liveness.STALE if silent < expectation.silence_after_seconds",
        test="TestACollectorThatHasGoneQuiet::test_a_collector_past_its_deadline_is_stale",
    ),
    Mutation(
        guard="never having reported is NO_EVIDENCE, not STALE",
        path=LIVENESS,
        before="return CollectorReport(expectation, Liveness.NO_EVIDENCE, None, None, moment)",
        after="return CollectorReport(expectation, Liveness.STALE, None, None, moment)",
        test=(
            "TestACollectorThatHasNeverReportedAtAll::"
            "test_a_collector_that_has_never_reported_is_no_evidence_not_stale"
        ),
    ),
    Mutation(
        guard="anything but LIVE is a FAULT on the board",
        path=LIVENESS,
        before=("Observation.HEALTHY if report.liveness is Liveness.LIVE else Observation.FAULT"),
        after="Observation.HEALTHY",
        test=(
            "TestACollectorThatHasGoneQuiet::test_silence_produces_a_fault_naming_the_collector_id"
        ),
    ),
    Mutation(
        guard="only this collector's own deliveries count as its arrivals",
        path=LIVENESS,
        before="if row.detail.get(COLLECTOR_ID) != collector_id:",
        after="if False:",
        test=(
            "TestWhatCountsAsAnArrival::"
            "test_another_collectors_arrival_does_not_prove_this_one_is_alive"
        ),
    ),
    Mutation(
        guard="arrivals are timed by received_at, not by the reading's own clock",
        path=LIVENESS,
        before="stamp = _parse_stamp(row.detail.get(RECEIVED_AT))",
        after="stamp = instant(row.read_at)",
        test=(
            "TestWhatCountsAsAnArrival::"
            "test_a_drained_spool_of_old_readings_still_proves_the_collector_ran"
        ),
    ),
    Mutation(
        guard="a row with no received_at never arrived",
        path=LIVENESS,
        before="stamp = _parse_stamp(row.detail.get(RECEIVED_AT))\n        if stamp is not None:",
        after="stamp = _parse_stamp(row.detail.get(RECEIVED_AT)) or instant(row.read_at)\n"
        "        if stamp is not None:",
        test=(
            "TestWhatCountsAsAnArrival::test_a_row_that_never_crossed_the_wire_proves_no_arrival"
        ),
    ),
    Mutation(
        guard="freshness is timed by read_at, not by when we heard about it",
        path=LIVENESS,
        before="age = (moment - instant(stored.read_at)).total_seconds()",
        after="age = (moment - (_parse_stamp(stored.detail.get(RECEIVED_AT))"
        " or instant(stored.read_at))).total_seconds()",
        test=("TestWhatCountsAsAnArrival::test_a_freshly_delivered_old_reading_is_still_stale"),
    ),
    Mutation(
        guard="a reading older than its cadence is UNOBSERVABLE",
        path=LIVENESS,
        before="return _STALE, _too_old(stored, expectation, age)",
        after="return _STALE, stored",
        test=(
            "TestASurfaceOlderThanItsCadence::"
            "test_a_stale_healthy_surface_reads_unobservable_never_healthy"
        ),
    ),
    Mutation(
        guard="a fresh reading is passed through untouched",
        path=LIVENESS,
        before="    return _FRESH, stored",
        after="    return _FRESH, _too_old(stored, expectation, age)",
        test=("TestASurfaceOlderThanItsCadence::test_a_fresh_surface_keeps_its_stored_observation"),
    ),
    Mutation(
        guard="a surface nothing has ever reported is unreported, not stale",
        path=LIVENESS,
        before="return _UNREPORTED, _never_reported(surface, expectation)",
        after="return _STALE, _never_reported(surface, expectation)",
        test=(
            "TestNothingReportedIsNotTheSameAsNoFaults::"
            "test_a_surface_nothing_has_ever_reported_is_unreported_not_stale"
        ),
    ),
    Mutation(
        guard="the deadline comes from the declared cadence and nothing else",
        path=EXPECTATIONS,
        before="return self.interval_seconds * (1.0 + self.grace_intervals)",
        after="return self.interval_seconds * 1000.0",
        test=(
            "TestTheDeadlineComesFromTheDeclarationNotTheHistory::"
            "test_a_collector_that_always_ran_hourly_is_stale_against_a_minute_cadence"
        ),
    ),
)


def _run(test: str) -> bool:
    """``True`` when the named test passes."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test}", "-q", "--no-header", "-p", "no:xdist"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode == 0


def _check(mutation: Mutation) -> bool:
    """Apply one mutation, run its test, restore. ``True`` when caught."""
    original = mutation.path.read_text()
    if mutation.before not in original:
        print(f"  SKIP  the guarded line has moved: {mutation.before[:60]!r}")
        return False

    restore = atexit.register(mutation.path.write_text, original)
    try:
        mutation.path.write_text(original.replace(mutation.before, mutation.after, 1))
        return not _run(mutation.test)
    finally:
        mutation.path.write_text(original)
        atexit.unregister(restore)


def main() -> int:
    print(f"mutation-checking {len(MUTATIONS)} guards\n")
    holes: list[Mutation] = []

    for mutation in MUTATIONS:
        print(f"- {mutation.guard}")
        if _check(mutation):
            print(f"  CAUGHT by {mutation.test.split('::')[-1]}\n")
        else:
            holes.append(mutation)
            print(f"  SURVIVED — {mutation.test.split('::')[-1]} did not object\n")

    if holes:
        print(f"{len(holes)} mutation(s) survived; those guards are unprotected")
        return 1
    print(f"all {len(MUTATIONS)} guards are load-bearing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
