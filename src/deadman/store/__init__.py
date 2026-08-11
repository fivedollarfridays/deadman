"""Durable evidence: one contract, two backends behind it.

See :mod:`deadman.store.base` for what a store promises, and why absence
returned from a read is a blind state rather than a null.

Importing this package pulls in no cloud SDK. :class:`FirestoreEvidenceStore`
is re-exported here and can be named, referenced and registered with nothing
installed; it reaches for the SDK when you construct one.
"""

from __future__ import annotations

from deadman.store.base import (
    DEFAULT_HISTORY_LIMIT,
    EvidenceStore,
    absent,
    decode,
    encode,
    row_id,
)
from deadman.store.firestore import FirestoreEvidenceStore, StoreSdkMissing
from deadman.store.memory import InMemoryEvidenceStore

#: Every backend that exists, by name. Registering one here is what subjects
#: it to the contract suite: ``tests/test_store_contract.py`` fails if a name
#: appears in this mapping without a factory wired in beside it, so a backend
#: cannot diverge from the contract by simply never being tested.
BACKENDS: dict[str, type] = {
    "firestore": FirestoreEvidenceStore,
    "memory": InMemoryEvidenceStore,
}

__all__ = [
    "BACKENDS",
    "DEFAULT_HISTORY_LIMIT",
    "EvidenceStore",
    "FirestoreEvidenceStore",
    "InMemoryEvidenceStore",
    "StoreSdkMissing",
    "absent",
    "decode",
    "encode",
    "row_id",
]
