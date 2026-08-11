"""An in-process stand-in for the Firestore client.

The suite is hermetic, so the real SDK is never installed and Firestore is
never reached. That would normally mean the Firestore backend's mapping code —
how a surface becomes a document path, how ordering is asked for, how a
snapshot becomes :class:`~deadman.evidence.model.Evidence` — is the one backend
nobody tests, which is exactly the divergence
``tests/test_store_contract.py`` exists to prevent.

So the double implements the *narrow slice* of the real API that
:mod:`deadman.store.firestore` actually calls, and the backend accepts an
injected client. The contract suite then runs against Firestore's real logic
with a fake transport underneath. Nothing here is implemented speculatively:
a method the backend does not call is a method whose behaviour this file would
be asserting from imagination.

Fidelity is the point, so the double reproduces two real behaviours that are
easy to get wrong and would otherwise only fail in production:

* a document id containing ``/`` is rejected, because it is a path separator.
  Surface ids like ``host:mac/disk`` contain one.
* streaming a collection yields only documents that have field data of their
  own. In Firestore a document that exists solely as the parent of a
  subcollection is not returned by a collection query.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class FakeSnapshot:
    """What ``stream()`` yields. Only ``to_dict`` is used by the backend."""

    def __init__(self, doc_id: str, data: dict[str, Any]) -> None:
        self.id = doc_id
        self._data = dict(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class FakeQuery:
    """An ordered result set, narrowable by ``limit`` and then streamed."""

    def __init__(self, snapshots: list[FakeSnapshot]) -> None:
        self._snapshots = snapshots

    def limit(self, count: int) -> FakeQuery:
        return FakeQuery(self._snapshots[:count])

    def stream(self) -> Iterator[FakeSnapshot]:
        return iter(list(self._snapshots))


class FakeCollection:
    def __init__(self) -> None:
        self._documents: dict[str, FakeDocument] = {}

    def document(self, doc_id: str) -> FakeDocument:
        if "/" in doc_id:
            raise ValueError(f"invalid document id {doc_id!r}: '/' is a path separator")
        return self._documents.setdefault(doc_id, FakeDocument(doc_id))

    def _snapshots(self) -> list[FakeSnapshot]:
        """Documents carrying field data. A subcollection parent has none."""
        return [
            FakeSnapshot(doc_id, doc.data)
            for doc_id, doc in self._documents.items()
            if doc.data is not None
        ]

    def order_by(self, field: str, direction: str = "ASCENDING") -> FakeQuery:
        ordered = sorted(self._snapshots(), key=lambda s: s.to_dict().get(field))
        if direction == "DESCENDING":
            ordered.reverse()
        return FakeQuery(ordered)

    def stream(self) -> Iterator[FakeSnapshot]:
        return iter(self._snapshots())


class FakeDocument:
    def __init__(self, doc_id: str) -> None:
        self.id = doc_id
        self.data: dict[str, Any] | None = None
        self._subcollections: dict[str, FakeCollection] = {}

    def set(self, payload: dict[str, Any]) -> None:
        """Whole-document write. Writing the same id twice leaves one document,
        which is what makes an identical row idempotent on this backend."""
        self.data = dict(payload)

    def collection(self, name: str) -> FakeCollection:
        return self._subcollections.setdefault(name, FakeCollection())


class FakeFirestoreClient:
    def __init__(self) -> None:
        self._collections: dict[str, FakeCollection] = {}

    def collection(self, name: str) -> FakeCollection:
        return self._collections.setdefault(name, FakeCollection())
