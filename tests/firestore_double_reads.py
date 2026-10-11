"""What a read of the Firestore double hands back: snapshots and queries.

Split from ``tests/firestore_double.py``, which holds the client, collection
and document, when a point read (``document.get()``) pushed that file past the
per-file function cap. See its module docstring for what the double is for and
which real behaviours it reproduces.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Any


class FakeSnapshot:
    """What ``stream()`` yields. Only ``to_dict`` is used by the backend."""

    def __init__(self, doc_id: str, data: dict[str, Any] | None) -> None:
        self.id = doc_id
        self.exists = data is not None
        self._data = None if data is None else copy.deepcopy(data)

    def to_dict(self) -> dict[str, Any] | None:
        """``None`` for a document that does not exist, as the real SDK does."""
        return None if self._data is None else copy.deepcopy(self._data)


class FakeQuery:
    """An ordered result set, narrowable by ``limit`` and then streamed."""

    def __init__(self, snapshots: list[FakeSnapshot]) -> None:
        self._snapshots = snapshots

    def limit(self, count: int) -> FakeQuery:
        return FakeQuery(self._snapshots[:count])

    def stream(self) -> Iterator[FakeSnapshot]:
        return iter(list(self._snapshots))
