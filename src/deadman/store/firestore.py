"""Firestore, the durable backend for the deployed service.

DM1 shipped a service whose evidence lived on Cloud Run's per-instance
filesystem, which means every cold start erased the history and a scale-to-zero
made the monitor forget it had ever seen anything. Storage that outlives the
instance is what turns "it swept" into "it has been sweeping".

**The SDK is imported inside the constructor, never at module scope.** Same
seam and the same reason as :class:`deadman.diagnose.gemini.GeminiClient`: the
package declares no runtime dependencies and the test suite must run with no
cloud SDK installed at all, so a top-level import would make that guarantee
depend on nobody having installed one. ``tests/test_store_seam.py`` fails
statically if this file ever grows one.

**Construction fails loudly; writes do not degrade.** A missing SDK is a
startup problem and is raised at startup. A store that fell back to dropping
evidence would produce the empty inbox that liveness cannot distinguish from a
healthy estate.

**Layout: one document per surface, rows in a subcollection beneath it.**
Partitioning by document path rather than by an indexed ``surface`` field
means every read this backend performs is an ordered range over one small
subcollection, needing no composite index and no field filter — nothing to
forget to deploy. The parent document carries the surface id as its only field
so :meth:`latest_per_surface` can enumerate surfaces with one collection read;
a document that existed solely as a subcollection parent would not be returned
by that query.

.. note::

   Like the ADK call shape in :mod:`deadman.diagnose.gemini`, the real SDK
   call shape here is **not exercised against live Firestore** — the suite is
   hermetic. What *is* exercised, by the full contract suite, is every line of
   mapping logic below, against the in-process double in
   ``tests/firestore_double.py``. The double reproduces the two behaviours
   most likely to bite: document ids may not contain ``/``, and a collection
   query returns only documents that carry field data of their own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from deadman.evidence.model import Evidence
from deadman.store.base import DEFAULT_HISTORY_LIMIT, absent, decode, encode, row_id

SOURCE = "store:firestore"

#: Top-level collection holding one document per surface.
COLLECTION = "evidence"

#: Subcollection beneath each surface document holding the rows themselves.
ROWS = "rows"

#: The literal value of ``google.cloud.firestore.Query.DESCENDING``. Spelled
#: out so ordering does not cost this module a module-scope SDK import.
DESCENDING = "DESCENDING"


class StoreSdkMissing(RuntimeError):
    """Raised at construction when the Firestore SDK is not installed."""


_INSTALL_HINT = (
    "google-cloud-firestore is not installed, so the service has nowhere "
    "durable to record evidence. Install it with: pip install 'deadman[firestore]'"
)


def surface_key(surface: str) -> str:
    """A surface id as a Firestore document id.

    Percent-encoded because surface ids are not constrained to Firestore's
    character set: ``host:mac/disk`` contains a slash, which is a path
    separator, and would silently address a different collection.
    """
    return quote(surface, safe="")


@dataclass
class FirestoreEvidenceStore:
    """An :class:`~deadman.store.base.EvidenceStore` backed by Firestore."""

    project: str | None = None
    collection: str = COLLECTION
    client: Any = None
    """Injected only by the contract suite. Left ``None`` in the service, so
    the SDK is reached for exactly where the seam says it should be."""

    def __post_init__(self) -> None:
        if self.client is not None:
            return
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise StoreSdkMissing(_INSTALL_HINT) from exc

        self.client = firestore.Client(project=self.project)

    def _surface_document(self, surface: str) -> Any:
        return self.client.collection(self.collection).document(surface_key(surface))

    def append(self, evidence: Evidence) -> None:
        """Write the row and index its surface.

        ``set`` on a content-derived id rather than ``add``: a re-sent spool
        rewrites the same document with the same payload instead of appending
        a second copy of one observation, so replay is idempotent without a
        read-modify-write race between two collectors.
        """
        document = self._surface_document(evidence.surface)
        document.set({"surface": evidence.surface})
        document.collection(ROWS).document(row_id(evidence)).set(encode(evidence))

    def history(self, surface: str, limit: int = DEFAULT_HISTORY_LIMIT) -> list[Evidence]:
        if limit <= 0:
            return []
        query = (
            self._surface_document(surface)
            .collection(ROWS)
            .order_by("read_at", direction=DESCENDING)
            .limit(limit)
        )
        newest_first = [decode(snapshot.to_dict()) for snapshot in query.stream()]
        newest_first.reverse()
        return newest_first

    def latest(self, surface: str) -> Evidence:
        newest = self.history(surface, limit=1)
        return newest[0] if newest else absent(surface, SOURCE)

    def latest_per_surface(self) -> dict[str, Evidence]:
        surfaces = sorted(
            surface
            for snapshot in self.client.collection(self.collection).stream()
            if (surface := (snapshot.to_dict() or {}).get("surface"))
        )
        return {surface: self.latest(surface) for surface in surfaces}
