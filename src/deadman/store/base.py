"""The evidence store contract.

Ingest writes through this, liveness and the board read through it, and
alerting records its own failures into it. Four consumers means four ways for
a backend's quirk to become a wrong verdict about the estate, so the contract
is stated here once and enforced once, in ``tests/test_store_contract.py``,
against every registered backend.

**Absence stays a state, never a null.** :meth:`EvidenceStore.latest` for a
surface with nothing stored returns ``UNOBSERVABLE`` evidence, not ``None``
and emphatically not a healthy row. This is :mod:`deadman.evidence.model`'s
rule applied one layer up: a store that has never heard from a surface has not
learned the surface is fine, it has learned it is blind to it. Returning
``None`` here would push that judgement onto every caller, and one caller
writing ``if not evidence: pass`` would silently reinstate the false green.

**Ordering is by ``read_at``, never by arrival.** A collector that could not
reach the service spools its evidence and re-sends later, so rows arrive out
of order by construction. A store that answered "latest" with "last written"
would report a recovered surface as still broken, or worse, the reverse.

**Identity is content, so replay is free.** Two rows with the same surface,
instant, method, observation, summary, source and detail are one observation
recorded twice, not two observations. :func:`row_id` makes that identity
explicit and deterministic, which is what lets a document backend write with
``set`` and be idempotent without a read-modify-write race. Rows that differ
only in ``read_at`` are kept apart, because held-duration is computed from
history and collapsing them would erase it.

No SDK is imported here or anywhere else at module scope in this package; see
:mod:`deadman.store.firestore`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from deadman.evidence.model import Evidence, Method, Observation, unobservable

#: How many rows a history read returns unless asked otherwise. Enough to see
#: a state change and how long it has held, small enough that a document
#: backend's read stays one bounded query.
DEFAULT_HISTORY_LIMIT = 50


@runtime_checkable
class EvidenceStore(Protocol):
    """Append-only evidence, readable newest-first per surface."""

    def append(self, evidence: Evidence) -> None:
        """Record one observation. Appending an identical row is a no-op."""
        ...

    def latest(self, surface: str) -> Evidence:
        """The newest row for ``surface`` by ``read_at``.

        Returns :func:`absent` when nothing is stored. Never ``None``.
        """
        ...

    def latest_per_surface(self) -> dict[str, Evidence]:
        """Newest row for every surface that has ever reported.

        Surfaces that have never reported are absent from the mapping rather
        than present with a synthesised row: this answers "who has reported",
        and inventing entries would answer a question the store cannot see.
        Reconciling that against the surfaces that *should* have reported is
        liveness's job, and it needs the two kept apart to do it.
        """
        ...

    def history(self, surface: str, limit: int = DEFAULT_HISTORY_LIMIT) -> list[Evidence]:
        """The newest ``limit`` rows for ``surface``, oldest first."""
        ...


def absent(surface: str, source: str) -> Evidence:
    """The blind row a backend returns for a surface it has nothing for."""
    return unobservable(
        surface=surface,
        source=source,
        why="no evidence has been stored for this surface",
    )


def instant(moment: datetime) -> datetime:
    """``read_at`` as an aware UTC datetime.

    Rows are sorted against each other, and comparing an aware datetime with a
    naive one raises. A naive value is read as UTC rather than as local time:
    every timestamp in this codebase is produced in UTC, so guessing the
    machine's timezone would invent an offset nobody intended.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def encode(evidence: Evidence) -> dict[str, Any]:
    """Evidence as a plain document, for any backend that stores documents.

    Shared rather than per-backend so two backends cannot disagree about how a
    ``Method`` is persisted. ``read_at`` becomes an ISO 8601 string normalised
    to UTC, which sorts lexicographically in the same order it sorts
    chronologically — that is what lets a document backend delegate ordering
    to the database instead of reading everything back to sort in Python.
    """
    return {
        "surface": evidence.surface,
        "observation": evidence.observation.value,
        "method": evidence.method.value,
        "summary": evidence.summary,
        "source": evidence.source,
        "read_at": instant(evidence.read_at).isoformat(),
        "detail": evidence.detail,
    }


def decode(row: Mapping[str, Any]) -> Evidence:
    """The inverse of :func:`encode`."""
    return Evidence(
        surface=row["surface"],
        observation=Observation(row["observation"]),
        method=Method(row["method"]),
        summary=row["summary"],
        source=row["source"],
        read_at=datetime.fromisoformat(row["read_at"]),
        detail=dict(row.get("detail") or {}),
    )


def row_id(evidence: Evidence) -> str:
    """A deterministic id for one observation, derived from its content.

    Hex, so it is usable verbatim as a document id on backends that restrict
    the character set.
    """
    canonical = json.dumps(encode(evidence), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
