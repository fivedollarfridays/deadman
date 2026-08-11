"""A dead collector and a healthy estate must not look the same.

This is the suite the sprint is least entitled to get wrong. Once evidence
arrives over a wire, an empty inbox has two readings — everything is fine, or
nothing is talking — and the whole point of the module under test is that the
board never gets to pick the comforting one.

**Every guard has a named test that fails when it is inverted.** The mapping,
so a reviewer can check it rather than trust it — guard first, then the test
that dies without it:

- ``silent > silence_after_seconds`` -> ``STALE``
  ``test_a_collector_past_its_deadline_is_stale``
- no arrivals at all -> ``NO_EVIDENCE``
  ``test_a_collector_that_has_never_reported_is_no_evidence_not_stale``
- anything but ``LIVE`` -> ``FAULT``
  ``test_silence_produces_a_fault_naming_the_collector_id``
- ``detail[collector_id]`` must match the expectation
  ``test_another_collectors_arrival_does_not_prove_this_one_is_alive``
- arrivals are timed by ``received_at``
  ``test_a_drained_spool_of_old_readings_still_proves_the_collector_ran``
- a row with no ``received_at`` is not an arrival
  ``test_a_row_that_never_crossed_the_wire_proves_no_arrival``
- freshness is timed by ``read_at``
  ``test_a_freshly_delivered_old_reading_is_still_stale``
- stale -> ``UNOBSERVABLE``
  ``test_a_stale_healthy_surface_reads_unobservable_never_healthy``
- fresh -> the stored row, untouched
  ``test_a_fresh_surface_keeps_its_stored_observation``
- never stored -> ``unreported``, not ``stale``
  ``test_a_surface_nothing_has_ever_reported_is_unreported_not_stale``
- the deadline is declared, never observed
  ``test_a_collector_that_always_ran_hourly_is_stale_against_a_minute_cadence``

Run them the way the task asks::

    PYTHONDONTWRITEBYTECODE=1 pytest tests/test_collector_liveness.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest.arrival import COLLECTOR_ID, RECEIVED_AT, on_arrival
from deadman.self_check import Liveness
from deadman.store.base import EvidenceStore
from deadman.store.memory import InMemoryEvidenceStore
from deadman.verify.collector_liveness import (
    LAST_OBSERVATION,
    LIVENESS,
    assess,
    assess_collector,
    collector_surface,
)
from deadman.verify.expectations import CollectorExpectation

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

DISK = "host:disk/"
BRIEF = "cron:morning-brief"

#: 15 minutes declared, so silence is called at 30: the cadence plus one whole
#: missed run. Every ``ago`` below is chosen against those two numbers.
MAC = CollectorExpectation("kevin-mac", interval_seconds=900, surfaces=(DISK, BRIEF))


def _ago(minutes: float) -> datetime:
    return NOW - timedelta(minutes=minutes)


def _reading(
    surface: str = DISK,
    observation: Observation = Observation.HEALTHY,
    read_at: datetime = NOW,
) -> Evidence:
    return Evidence(
        surface=surface,
        observation=observation,
        method=Method.LOCAL_ARTIFACT,
        summary=f"{surface} is {observation.value}",
        source="test",
        read_at=read_at,
    )


def _deliver(
    store: EvidenceStore,
    surface: str = DISK,
    observation: Observation = Observation.HEALTHY,
    read_at: datetime = NOW,
    received_at: datetime | None = None,
    collector_id: str = "kevin-mac",
) -> None:
    """Store a row exactly as ``POST /evidence`` would have stored it.

    Through :func:`on_arrival` rather than hand-built detail keys, so these
    tests break if ingest ever stops recording who reported and when we heard.
    """
    store.append(
        on_arrival(
            _reading(surface, observation, read_at),
            collector_id,
            received_at if received_at is not None else read_at,
        )
    )


@pytest.fixture
def store() -> InMemoryEvidenceStore:
    return InMemoryEvidenceStore()


class TestACollectorThatHasGoneQuiet:
    def test_a_collector_inside_its_deadline_is_live(self, store: InMemoryEvidenceStore) -> None:
        _deliver(store, read_at=_ago(10))

        report = assess_collector(store, MAC, NOW)

        assert report.liveness is Liveness.LIVE

    def test_a_collector_past_its_deadline_is_stale(self, store: InMemoryEvidenceStore) -> None:
        """31 minutes of silence against a declared 15-minute cadence: the
        cadence plus one whole missed run has elapsed."""
        _deliver(store, read_at=_ago(31))

        report = assess_collector(store, MAC, NOW)

        assert report.liveness is Liveness.STALE

    def test_a_late_but_not_missing_run_is_not_yet_an_incident(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """20 minutes: one sweep has been missed, the next has not. Alarming
        here is how a monitor teaches its reader to ignore it."""
        _deliver(store, read_at=_ago(20))

        assert assess_collector(store, MAC, NOW).liveness is Liveness.LIVE

    def test_silence_produces_a_fault_naming_the_collector_id(
        self, store: InMemoryEvidenceStore
    ) -> None:
        _deliver(store, read_at=_ago(31))

        (row,) = assess(store, [MAC], NOW).collectors

        assert row.observation is Observation.FAULT
        assert row.surface == collector_surface("kevin-mac")
        assert "kevin-mac" in row.summary

    def test_a_reporting_collector_is_healthy_on_the_board(
        self, store: InMemoryEvidenceStore
    ) -> None:
        _deliver(store, read_at=_ago(5))

        (row,) = assess(store, [MAC], NOW).collectors

        assert row.observation is Observation.HEALTHY


class TestACollectorThatHasNeverReportedAtAll:
    def test_a_collector_that_has_never_reported_is_no_evidence_not_stale(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """DM1.11's distinction, one level up. "It stopped" and "it was never
        installed, or it is posting to the wrong URL" are different mornings."""
        report = assess_collector(store, MAC, NOW)

        assert report.liveness is Liveness.NO_EVIDENCE
        assert report.last_report_at is None

    def test_never_reported_also_faults_rather_than_going_quiet(
        self, store: InMemoryEvidenceStore
    ) -> None:
        (row,) = assess(store, [MAC], NOW).collectors

        assert row.observation is Observation.FAULT
        assert "kevin-mac" in row.summary

    def test_the_two_silences_are_distinguishable_on_the_board(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """Both alarm, and a reader can still tell which one they are in —
        the whole reason the state is carried rather than collapsed to a
        boolean."""
        quiet = InMemoryEvidenceStore()
        _deliver(quiet, read_at=_ago(31))

        (never,) = assess(store, [MAC], NOW).collectors
        (stopped,) = assess(quiet, [MAC], NOW).collectors

        assert never.detail[LIVENESS] == Liveness.NO_EVIDENCE.value
        assert stopped.detail[LIVENESS] == Liveness.STALE.value
        assert never.summary != stopped.summary


class TestTheDeadlineComesFromTheDeclarationNotTheHistory:
    def test_a_collector_that_always_ran_hourly_is_stale_against_a_minute_cadence(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """The failure this design refuses: a collector whose observed gaps
        are hours long, declared to report every minute. An implementation
        that inferred cadence from history would call this live, because it
        would have learned to expect the silence."""
        for hours_ago in range(24, 0, -1):
            _deliver(store, read_at=NOW - timedelta(hours=hours_ago))
        minutely = CollectorExpectation("kevin-mac", interval_seconds=60, surfaces=(DISK, BRIEF))

        assert assess_collector(store, minutely, NOW).liveness is Liveness.STALE

    def test_a_long_healthy_history_does_not_widen_the_window(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """A collector that dies slowly must not be able to teach the monitor
        that its new, longer silences are normal."""
        for minutes_ago in range(300, 30, -10):
            _deliver(store, read_at=_ago(minutes_ago))
        _deliver(store, read_at=_ago(31))

        assert assess_collector(store, MAC, NOW).liveness is Liveness.STALE


class TestWhatCountsAsAnArrival:
    def test_a_drained_spool_of_old_readings_still_proves_the_collector_ran(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """Liveness is about delivery, freshness is about reading, and a
        store-and-forward collector separates them by construction: it came
        back up and shipped a day-old sweep. It is alive. Its evidence is
        not fresh. Both are true and the board says both."""
        _deliver(store, read_at=_ago(1440), received_at=_ago(2))

        report = assess(store, [MAC], NOW)

        assert assess_collector(store, MAC, NOW).liveness is Liveness.LIVE
        assert report.stale == 1

    def test_a_freshly_delivered_old_reading_is_still_stale(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """The same fact from the surface's side: a recent delivery does not
        make an old reading current. Timing freshness by ``received_at``
        would let a collector refresh the board by re-sending its spool."""
        _deliver(store, read_at=_ago(1440), received_at=NOW)

        (row,) = [e for e in assess(store, [MAC], NOW).surfaces if e.surface == DISK]

        assert row.observation is Observation.UNOBSERVABLE

    def test_another_collectors_arrival_does_not_prove_this_one_is_alive(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """Two collectors can report the same surface id in a mis-declared
        estate. Counting anyone's delivery as everyone's liveness is how a
        dead collector hides behind a working one."""
        _deliver(store, read_at=_ago(1), collector_id="someone-elses-mac")

        assert assess_collector(store, MAC, NOW).liveness is Liveness.NO_EVIDENCE

    def test_a_row_that_never_crossed_the_wire_proves_no_arrival(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """A row written into the store directly — a local sweep, a fixture,
        a backfill — carries no ``received_at``. Falling back to ``read_at``
        here would let the service's own writes forge a collector's
        heartbeat.

        The row is attributed to this collector on purpose, so the only guard
        standing between it and a forged heartbeat is the ``received_at``
        check: if the id filter were the thing making this pass, the test
        would not be testing what it says it tests.
        """
        row = _reading(read_at=NOW)
        store.append(
            Evidence(
                surface=row.surface,
                observation=row.observation,
                method=row.method,
                summary=row.summary,
                source=row.source,
                read_at=row.read_at,
                detail={COLLECTOR_ID: "kevin-mac"},
            )
        )

        assert assess_collector(store, MAC, NOW).liveness is Liveness.NO_EVIDENCE

    def test_the_newest_arrival_wins_across_the_collectors_surfaces(
        self, store: InMemoryEvidenceStore
    ) -> None:
        _deliver(store, surface=DISK, read_at=_ago(90), received_at=_ago(90))
        _deliver(store, surface=BRIEF, read_at=_ago(3), received_at=_ago(3))

        assert assess_collector(store, MAC, NOW).liveness is Liveness.LIVE


class TestASurfaceOlderThanItsCadence:
    def test_a_stale_healthy_surface_reads_unobservable_never_healthy(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """The single most important assertion in this file. The last thing
        we heard was good news; we heard it 24 hours ago on a 15-minute
        cadence, so it is not news about now."""
        _deliver(store, surface=DISK, observation=Observation.HEALTHY, read_at=_ago(1440))

        (row,) = [e for e in assess(store, [MAC], NOW).surfaces if e.surface == DISK]

        assert row.observation is Observation.UNOBSERVABLE
        assert row.observation is not Observation.HEALTHY

    def test_a_stale_fault_also_reads_unobservable_but_remembers_what_it_said(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """Downgrading a stale fault is not losing an alarm: blind is its own
        alarm, the collector is already faulting beside it, and the last
        observation is carried in the row rather than thrown away."""
        _deliver(store, surface=DISK, observation=Observation.FAULT, read_at=_ago(1440))

        (row,) = [e for e in assess(store, [MAC], NOW).surfaces if e.surface == DISK]

        assert row.observation is Observation.UNOBSERVABLE
        assert row.detail[LAST_OBSERVATION] == Observation.FAULT.value

    def test_a_stale_row_names_the_surface_its_age_and_its_cadence(
        self, store: InMemoryEvidenceStore
    ) -> None:
        _deliver(store, surface=DISK, read_at=_ago(1440))

        (row,) = [e for e in assess(store, [MAC], NOW).surfaces if e.surface == DISK]

        assert DISK in row.summary
        assert row.detail[COLLECTOR_ID] == "kevin-mac"
        assert row.detail["cadence_seconds"] == MAC.interval_seconds

    def test_a_fresh_surface_keeps_its_stored_observation(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """Freshness judges the reading's age, not its content: a fresh fault
        stays a fault, verbatim, including the arrival detail ingest wrote."""
        _deliver(store, surface=DISK, observation=Observation.FAULT, read_at=_ago(2))

        (row,) = [e for e in assess(store, [MAC], NOW).surfaces if e.surface == DISK]

        assert row.observation is Observation.FAULT
        assert row.detail[RECEIVED_AT]


class TestNothingReportedIsNotTheSameAsNoFaults:
    def test_a_surface_nothing_has_ever_reported_is_unreported_not_stale(
        self, store: InMemoryEvidenceStore
    ) -> None:
        _deliver(store, surface=DISK, read_at=_ago(2))

        report = assess(store, [MAC], NOW)

        assert report.unreported == 1
        assert report.stale == 0
        assert report.fresh == 1

    def test_an_unreported_surface_gets_a_row_that_says_so(
        self, store: InMemoryEvidenceStore
    ) -> None:
        (row,) = [e for e in assess(store, [MAC], NOW).surfaces if e.surface == BRIEF]

        assert row.observation is Observation.UNOBSERVABLE
        assert row.detail[LIVENESS] == Liveness.NO_EVIDENCE.value
        assert BRIEF in row.summary

    def test_an_empty_store_reports_every_declared_surface_as_unreported(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """The quiet board, refused. Nothing has arrived, so nothing is
        healthy, and the count that says so is not the fault count."""
        report = assess(store, [MAC], NOW)

        assert report.unreported == 2
        assert report.fresh == 0
        assert not [e for e in report.surfaces if e.observation is Observation.HEALTHY]

    def test_evidence_for_an_undeclared_surface_is_listed_rather_than_dropped(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """Something reported a surface no collector declares. That is a
        configuration gap; hiding it would make the board quietly incomplete,
        and judging its freshness would mean inventing a cadence for it."""
        _deliver(store, surface="host:unknown", read_at=_ago(1))

        assert assess(store, [MAC], NOW).undeclared == ("host:unknown",)


class TestLivenessReadsThroughTheStore:
    def test_it_touches_nothing_but_the_store_protocol(self, store: InMemoryEvidenceStore) -> None:
        """AC: liveness reads through the DM2.1 ``EvidenceStore``, not a
        local filesystem. A recorder proves the positive half — every read
        went through a protocol method."""
        _deliver(store, read_at=_ago(2))
        recorder = _RecordingStore(store)

        assess(recorder, [MAC], NOW)

        assert recorder.calls
        assert set(recorder.calls) <= {"latest", "latest_per_surface", "history"}

    def test_the_module_never_opens_a_file(self) -> None:
        """And the negative half, statically: a later edit that reaches for a
        path instead of the store fails here rather than on the one deploy
        whose filesystem is empty."""
        import inspect

        from deadman.verify import collector_liveness

        source = inspect.getsource(collector_liveness)

        for forbidden in ("import os", "pathlib", "open(", ".read_text("):
            assert forbidden not in source, f"{forbidden} has no business in liveness"


class _RecordingStore:
    """An :class:`EvidenceStore` that notes which contract methods were used."""

    def __init__(self, inner: EvidenceStore) -> None:
        self._inner = inner
        self.calls: list[str] = []

    def append(self, evidence: Evidence) -> None:
        self.calls.append("append")
        self._inner.append(evidence)

    def latest(self, surface: str) -> Evidence:
        self.calls.append("latest")
        return self._inner.latest(surface)

    def latest_per_surface(self) -> dict[str, Evidence]:
        self.calls.append("latest_per_surface")
        return self._inner.latest_per_surface()

    def history(self, surface: str, limit: int = 50) -> list[Evidence]:
        self.calls.append("history")
        return self._inner.history(surface, limit)
