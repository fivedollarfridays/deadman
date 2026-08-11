"""``POST /evidence``: the only way evidence enters the service from outside.

The HTTP is the boring part. What this module is actually responsible for is
the order of operations, and each step is placed where it is because the
alternative fails in a way that looks fine:

1. **Bound the body before reading it.** A declared length over the cap is
   refused, and the read itself is capped too, so a lying ``Content-Length``
   cannot turn into an unbounded read.
2. **Verify the MAC over the raw bytes, before parsing.** Nothing
   unauthenticated is ever interpreted, so a malformed-body path cannot be
   reached by an unauthenticated caller.
3. **Parse strictly** (:mod:`deadman.ingest.wire`), so remote input that is
   not a batch is a 4xx and never a traceback.
4. **Check freshness**, using the ``signed_at`` that step 2 just proved
   unedited.
5. **Downgrade, annotate and store**, and only then answer 200 — the response
   is what tells a collector its spool is durable and may be dropped, so it
   must not be sent before the writes have happened.

Every refusal path returns before step 5, which is what makes "rejected and
stored nothing" a property of the structure rather than of a check somebody
remembers to write.

**Replay is deduplicated on the observation, not on the stored row.** An
honest collector that could not reach the service re-sends, and it must be
able to: refusing retries would drop evidence exactly when the network is
already unreliable. But a re-sent row arrives at a new time, and the stored
row records that arrival time, so the store's own content-addressed identity
sees two different rows. ``detail['wire_row_id']`` carries the identity of the
observation itself and is what gets compared here.

That comparison reads back a bounded slice of history
(:data:`REPLAY_LOOKBACK` rows per surface), which is the one honest limit in
this module: a batch re-sent after that many newer rows for the same surface
will store a second copy. It will be a *recognisable* second copy — same
``wire_row_id``, same ``read_at``, later ``received_at`` — so a reader can
still collapse it, rather than a silent doubling of the trend.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from deadman.ingest.arrival import WIRE_ROW_ID, on_arrival
from deadman.ingest.auth import (
    SIGNATURE_ENVIRON_KEY,
    AuthError,
    check_freshness,
    check_signature,
)
from deadman.ingest.wire import Batch, WireError, loads
from deadman.store.base import EvidenceStore, row_id

#: The path a collector posts to.
EVIDENCE_PATH = "/evidence"

#: Largest body accepted, in bytes. A sweep of a handful of surfaces is a few
#: kilobytes; this leaves three orders of magnitude of headroom and still
#: bounds what one request can cost.
MAX_BODY_BYTES = 256 * 1024

#: How far back per surface the replay check looks. See the module docstring
#: for what a replay older than this does — and, deliberately, does not do.
REPLAY_LOOKBACK = 200

_STATUS_BAD_REQUEST = "400 Bad Request"
_STATUS_UNAUTHORIZED = "401 Unauthorized"
_STATUS_TOO_LARGE = "413 Payload Too Large"
_STATUS_OK = "200 OK"


class BodyTooLarge(Exception):
    """The request body exceeds :data:`MAX_BODY_BYTES`."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IngestEndpoint:
    """Handles one ``POST /evidence``, writing through an
    :class:`~deadman.store.base.EvidenceStore`."""

    store: EvidenceStore
    secret: bytes
    clock: Callable[[], datetime] = field(default=_now)
    expectations: tuple[Any, ...] | None = None
    """Declared collector duties, from :mod:`deadman.verify.expectations`.

    When present, a batch may only carry surfaces its own collector declared.
    One shared secret is distributed to every collector (per-collector secrets
    are DM3), so without this a compromise of any one machine could forge
    ``HEALTHY`` for *every* surface in the estate, including surfaces that
    machine never sweeps — silently disarming the monitor rather than breaking
    it. The declaration already exists for liveness, so binding to it is free.

    ``None`` means no binding, which keeps an estate that has not declared
    anything yet able to ingest.
    """

    def handle(self, environ: dict) -> tuple[str, dict[str, Any]]:
        """``(status, payload)`` for one request. Never raises for bad input.

        Returns the pair rather than calling ``start_response`` so the HTTP
        plumbing stays in :mod:`deadman.service` and this stays testable as
        what it is: a decision about whether to believe someone.
        """
        received_at = self.clock()
        try:
            raw = _read_body(environ)
            check_signature(raw, environ.get(SIGNATURE_ENVIRON_KEY), self.secret)
            batch = loads(raw, now=received_at)
            check_freshness(batch.signed_at, received_at)
            self.check_declared(batch)
        except BodyTooLarge as exc:
            return _STATUS_TOO_LARGE, {"error": str(exc)}
        except AuthError as exc:
            return _STATUS_UNAUTHORIZED, {"error": str(exc)}
        except WireError as exc:
            return _STATUS_BAD_REQUEST, {"error": str(exc)}

        stored, duplicates = self._record(batch, received_at)
        return _STATUS_OK, {
            "collector_id": batch.collector_id,
            "accepted": len(batch.rows),
            "stored": stored,
            "duplicates": duplicates,
        }

    def check_declared(self, batch: Batch) -> None:
        """Raise :class:`WireError` if a batch reports a surface its collector
        never declared.

        A :class:`WireError` rather than an auth error on purpose: the caller
        proved it holds the shared secret, so this is a statement about the
        *content* of an authenticated request, not about who sent it.
        """
        if self.expectations is None:
            return
        declared: set[str] = set()
        for expectation in self.expectations:
            if expectation.collector_id == batch.collector_id:
                declared.update(expectation.surfaces)
        undeclared = sorted({row.surface for row in batch.rows} - declared)
        if undeclared:
            raise WireError(
                f"collector {batch.collector_id!r} did not declare "
                f"{', '.join(repr(s) for s in undeclared)}"
            )

    def _record(self, batch: Batch, received_at: datetime) -> tuple[int, int]:
        """Store what is new. One arrival time for the whole request, read
        before any of it, so every row of one delivery agrees on when it
        landed."""
        seen = self._observations_already_held(batch)
        stored = duplicates = 0
        for row in batch.rows:
            identity = row_id(row)
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            self.store.append(on_arrival(row, batch.collector_id, received_at))
            stored += 1
        return stored, duplicates

    def _observations_already_held(self, batch: Batch) -> set[str]:
        """Wire ids this store has already recorded for the batch's surfaces."""
        held: set[str] = set()
        for surface in {row.surface for row in batch.rows}:
            for evidence in self.store.history(surface, limit=REPLAY_LOOKBACK):
                wire_id = evidence.detail.get(WIRE_ROW_ID)
                if isinstance(wire_id, str):
                    held.add(wire_id)
        return held


def _read_body(environ: dict) -> bytes:
    """The request body, or a refusal. Never an unbounded read."""
    declared = str(environ.get("CONTENT_LENGTH") or "").strip()
    if declared:
        try:
            length = int(declared)
        except ValueError as exc:
            raise WireError(f"Content-Length {declared!r} is not an integer") from exc
        if length > MAX_BODY_BYTES:
            raise BodyTooLarge(f"body of {length} bytes exceeds the {MAX_BODY_BYTES} byte cap")

    stream = environ.get("wsgi.input")
    raw = stream.read(MAX_BODY_BYTES + 1) if stream is not None else b""
    if len(raw) > MAX_BODY_BYTES:
        raise BodyTooLarge(f"body exceeds the {MAX_BODY_BYTES} byte cap")
    return raw
