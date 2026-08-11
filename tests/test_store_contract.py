"""One contract suite, run against every registered backend.

The store is consumed by ingest, liveness, the board and alerting, so a
backend that quietly disagrees with the others about ordering, absence or
duplicate rows would not fail here — it would fail as a wrong verdict about
the estate, months later, on the one backend nobody tests locally.

So there is no per-backend test file. Every test below is parametrised over
:data:`deadman.store.BACKENDS`, and
:func:`test_every_registered_backend_is_covered_by_this_suite` fails the
moment a backend is registered without being wired in here. Adding a backend
and skipping its contract is not something you can do by omission.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest
from firestore_double import FakeFirestoreClient

from deadman.evidence.model import Evidence, Method, Observation
from deadman.store import BACKENDS, EvidenceStore, FirestoreEvidenceStore, InMemoryEvidenceStore

#: How the contract suite builds each registered backend. Firestore gets the
#: in-process double from ``tests/firestore_double.py``; every other backend
#: is constructed as the deployed service would construct it.
FACTORIES: dict[str, Callable[[], EvidenceStore]] = {
    "memory": InMemoryEvidenceStore,
    "firestore": lambda: FirestoreEvidenceStore(client=FakeFirestoreClient()),
}

T0 = datetime(2026, 8, 11, 6, 0, tzinfo=timezone.utc)


def _evidence(
    surface: str = "test:surface",
    observation: Observation = Observation.HEALTHY,
    method: Method = Method.LOCAL_ARTIFACT,
    read_at: datetime = T0,
    **detail: object,
) -> Evidence:
    return Evidence(
        surface=surface,
        observation=observation,
        method=method,
        summary=f"{surface} is {observation.value}",
        source="test",
        read_at=read_at,
        detail=dict(detail),
    )


@pytest.fixture(params=sorted(FACTORIES))
def store(request: pytest.FixtureRequest) -> EvidenceStore:
    return FACTORIES[request.param]()


def test_every_registered_backend_is_covered_by_this_suite() -> None:
    """The guard that makes this a contract rather than a courtesy."""
    assert set(BACKENDS) == set(FACTORIES)


def test_backend_satisfies_the_protocol(store: EvidenceStore) -> None:
    assert isinstance(store, EvidenceStore)


def test_append_then_read_latest_round_trips_every_field(store: EvidenceStore) -> None:
    original = _evidence(
        surface="host:mac/disk",
        observation=Observation.FAULT,
        method=Method.DESTINATION_API,
        read_at=T0,
        free_bytes=1234,
        nested={"status": 401, "body": "expired token"},
    )

    store.append(original)
    restored = store.latest("host:mac/disk")

    assert restored.surface == original.surface
    assert restored.observation is original.observation
    assert restored.method is original.method
    assert restored.read_at == original.read_at
    assert restored.detail == original.detail
    assert restored.summary == original.summary
    assert restored.source == original.source


def test_reading_a_surface_with_no_rows_returns_an_explicit_absence(store: EvidenceStore) -> None:
    """Never ``None`` and never a synthesised healthy row.

    "We have nothing stored for this surface" is a statement about our
    visibility, not about the surface, and the only honest way to say it in
    this codebase's vocabulary is ``UNOBSERVABLE``.
    """
    absent = store.latest("test:never-reported")

    assert absent.observation is Observation.UNOBSERVABLE
    assert absent.observation is not Observation.HEALTHY
    assert absent.is_blind
    assert absent.surface == "test:never-reported"
    assert "no evidence" in absent.summary


def test_latest_is_the_newest_by_read_at_not_the_last_appended(store: EvidenceStore) -> None:
    """A collector's spool re-sends out of order; arrival order is not time."""
    newest = _evidence(observation=Observation.FAULT, read_at=T0 + timedelta(hours=2))
    older = _evidence(observation=Observation.HEALTHY, read_at=T0)

    store.append(newest)
    store.append(older)

    assert store.latest("test:surface").observation is Observation.FAULT
    assert store.latest("test:surface").read_at == T0 + timedelta(hours=2)


def test_latest_per_surface_returns_one_newest_row_for_each_surface(store: EvidenceStore) -> None:
    store.append(_evidence(surface="a:one", observation=Observation.HEALTHY, read_at=T0))
    store.append(
        _evidence(surface="a:one", observation=Observation.FAULT, read_at=T0 + timedelta(minutes=5))
    )
    store.append(_evidence(surface="b:two", observation=Observation.UNOBSERVABLE, read_at=T0))

    latest = store.latest_per_surface()

    assert set(latest) == {"a:one", "b:two"}
    assert latest["a:one"].observation is Observation.FAULT
    assert latest["b:two"].observation is Observation.UNOBSERVABLE


def test_latest_per_surface_is_empty_when_nothing_has_been_stored(store: EvidenceStore) -> None:
    """An empty estate reads as empty, not as a healthy one."""
    assert store.latest_per_surface() == {}


def test_history_is_chronological_and_capped_to_the_newest_rows(store: EvidenceStore) -> None:
    for minute in range(5):
        store.append(_evidence(read_at=T0 + timedelta(minutes=minute), n=minute))

    full = store.history("test:surface")
    capped = store.history("test:surface", limit=2)

    assert [e.read_at for e in full] == sorted(e.read_at for e in full)
    assert len(full) == 5
    assert [e.detail["n"] for e in capped] == [3, 4]


def test_history_for_an_unreported_surface_is_empty(store: EvidenceStore) -> None:
    assert store.history("test:never-reported") == []


def test_appending_an_identical_row_twice_stores_it_once(store: EvidenceStore) -> None:
    """Replay safety lives here, not in each caller.

    A collector that cannot reach the service re-sends its spool, so the same
    observation arrives more than once. Two copies of one reading would double
    the history and manufacture a trend out of a network blip.
    """
    evidence = _evidence(read_at=T0)

    store.append(evidence)
    store.append(evidence)

    assert len(store.history("test:surface")) == 1


def test_rows_differing_only_in_read_at_are_kept_apart(store: EvidenceStore) -> None:
    """The other half of the identity rule: same reading, different moment, is
    two observations. Deduplicating those would erase the history the board
    computes held-duration from."""
    store.append(_evidence(read_at=T0))
    store.append(_evidence(read_at=T0 + timedelta(seconds=1)))

    assert len(store.history("test:surface")) == 2
