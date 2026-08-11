"""Store-and-forward: evidence a delivery attempt failed to ship is never dropped.

**Nothing about a spooled batch lives in process memory.** Every method here
reads or writes :attr:`Spool.path` directly, which is what makes the spool
survive a process restart for free: a new :class:`Spool` built over the same
path sees exactly what a prior process left behind, because there is nowhere
else the prior process could have kept it. A queue held in a Python list
would not survive the crash a spool exists to survive.

**One file per failed batch, named so directory order is delivery order.**
The timestamp prefix makes :meth:`Spool.pending` return oldest-first with
nothing more than a sort of filenames — no index file to keep in sync with
the batches it indexes, and nothing to corrupt independently of the batches
themselves.

**Rows are stored with the store's own encoding** (:func:`deadman.store.
base.encode`/:func:`decode`), the same document shape :mod:`deadman.ingest.
wire` builds on. A spooled row and a row about to be signed are the same
object on both sides of a restart.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from deadman.evidence.model import Evidence
from deadman.store.base import decode, encode


@dataclass(frozen=True)
class SpoolItem:
    """One batch waiting on disk, and where to find it to drop it later."""

    path: Path
    rows: tuple[Evidence, ...]


@dataclass
class Spool:
    """A directory of undelivered batches. The directory *is* the state."""

    path: Path

    def enqueue(self, rows: tuple[Evidence, ...], when: datetime | None = None) -> None:
        """Write one failed batch to disk.

        A no-op for an empty batch: there is nothing to redeliver, and an
        empty spool file would only be something for :meth:`pending` to skip
        over later. Not best-effort — a write that fails here raises, because
        swallowing it would silently do the one thing this module exists to
        prevent: dropping evidence.
        """
        if not rows:
            return
        self.path.mkdir(parents=True, exist_ok=True)
        moment = when or datetime.now(timezone.utc)
        name = f"{moment.strftime('%Y%m%dT%H%M%S%f')}-{uuid.uuid4().hex[:8]}.json"
        payload = [encode(row) for row in rows]
        (self.path / name).write_text(json.dumps(payload))

    def pending(self) -> list[SpoolItem]:
        """Every undelivered batch, oldest first, read straight from disk."""
        if not self.path.is_dir():
            return []
        items = []
        for file in sorted(self.path.glob("*.json")):
            try:
                payload = json.loads(file.read_text())
                rows = tuple(decode(row) for row in payload)
            except (OSError, ValueError, KeyError):
                continue  # a torn spool file loses one batch, not the queue
            items.append(SpoolItem(path=file, rows=rows))
        return items

    def drop(self, item: SpoolItem) -> None:
        """Remove a batch once it has actually been delivered."""
        item.path.unlink(missing_ok=True)
