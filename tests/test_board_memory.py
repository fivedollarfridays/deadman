"""The board grows a memory: held-duration and collector attribution.

``EvidenceStore.history`` existed since DM2.1 for exactly this task (see its
own docstring). This is what actually reads it: how long a surface has held
its current state, walked back through stored history to the last state
change rather than restated from the newest row alone, and which collector
said so.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest.arrival import on_arrival
from deadman.service import build_board
from deadman.store.base import DEFAULT_HISTORY_LIMIT
from deadman.store.memory import InMemoryEvidenceStore
from deadman.verify.collector_liveness import assess
from deadman.verify.expectations import CollectorExpectation

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
SURFACE = "host:mac/disk"


def _row(observation: Observation, read_at: datetime, **detail: object) -> Evidence:
    return Evidence(
        surface=SURFACE,
        observation=observation,
        method=Method.LOCAL_ARTIFACT,
        summary=f"{SURFACE}: {observation.value}",
        source="test",
        read_at=read_at,
        detail=detail,
    )


class _FakeProbe:
    def __init__(self, evidence: Evidence) -> None:
        self._evidence = evidence

    @property
    def surface(self) -> str:
        return self._evidence.surface

    @property
    def question(self) -> str:
        return "is it fine?"

    def observe(self) -> Evidence:
        return self._evidence


def _surface_row(board: dict) -> dict:
    return next(row for row in board["surfaces"] if row["surface"] == SURFACE)


class TestHeldDuration:
    def test_held_since_walks_back_to_the_last_state_change(self):
        """Three FAULT rows follow one HEALTHY row. The newest FAULT reading
        is recent, but the state itself began at the oldest FAULT row — held
        duration must reach back that far, not restate the newest read_at."""
        store = InMemoryEvidenceStore()
        store.append(_row(Observation.HEALTHY, NOW - timedelta(days=10)))
        changed_at = NOW - timedelta(days=3)
        store.append(_row(Observation.FAULT, changed_at))
        store.append(_row(Observation.FAULT, NOW - timedelta(days=2)))
        newest = _row(Observation.FAULT, NOW - timedelta(minutes=5))
        store.append(newest)

        board = build_board([_FakeProbe(newest)], store=store)

        row = _surface_row(board)
        assert row["held_since"] == changed_at.isoformat()
        expected_seconds = (newest.read_at - changed_at).total_seconds()
        assert row["held_seconds"] == pytest.approx(round(expected_seconds, 1))

    def test_a_single_stored_row_renders_a_held_duration_without_error(self):
        store = InMemoryEvidenceStore()
        only = _row(Observation.HEALTHY, NOW)
        store.append(only)

        board = build_board([_FakeProbe(only)], store=store)

        row = _surface_row(board)
        assert row["held_since"] == NOW.isoformat()
        assert row["held_seconds"] == 0.0

    def test_a_surface_with_no_store_still_renders_a_held_duration(self):
        """No store at all (the common local-sweep case): held-duration must
        degrade gracefully to zero rather than raising."""
        evidence = _row(Observation.HEALTHY, NOW)

        board = build_board([_FakeProbe(evidence)])

        row = _surface_row(board)
        assert row["held_since"] == NOW.isoformat()
        assert row["held_seconds"] == 0.0


class TestHistoryReadIsBounded:
    def test_build_board_asks_for_a_bounded_history_not_an_unbounded_one(self):
        calls: list[int] = []

        class _SpyStore(InMemoryEvidenceStore):
            def history(self, surface: str, limit: int = DEFAULT_HISTORY_LIMIT):
                calls.append(limit)
                return super().history(surface, limit=limit)

        store = _SpyStore()
        evidence = _row(Observation.HEALTHY, NOW)
        store.append(evidence)

        build_board([_FakeProbe(evidence)], store=store)

        assert calls == [DEFAULT_HISTORY_LIMIT]


class TestReportedByOnTheBoard:
    def test_a_collector_reported_row_names_its_collector(self):
        store = InMemoryEvidenceStore()
        arrived = on_arrival(_row(Observation.HEALTHY, NOW), "kevin-mac", NOW)
        store.append(arrived)

        board = build_board([_FakeProbe(arrived)], store=store)

        row = _surface_row(board)
        assert row["reported_by"] == "kevin-mac"

    def test_a_locally_swept_probe_carries_no_reported_by(self):
        evidence = _row(Observation.HEALTHY, NOW)

        board = build_board([_FakeProbe(evidence)])

        row = _surface_row(board)
        assert "reported_by" not in row


class TestCountsStayPartitioned:
    def test_blind_and_unreported_are_not_folded_into_healthy(self):
        store = InMemoryEvidenceStore()
        expectation = CollectorExpectation("kevin-mac", interval_seconds=900, surfaces=(SURFACE,))

        board = build_board([], liveness=assess(store, [expectation], NOW), store=store)

        assert board["healthy_count"] == 0
        assert board["unreported_count"] == 1
        assert board["blind_count"] >= 1
