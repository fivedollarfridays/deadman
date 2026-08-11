"""The wire format: evidence as bytes, and bytes back to evidence.

**The row format is the store's document format, deliberately.** :func:`encode`
and :func:`decode` in :mod:`deadman.store.base` already define how an
``Evidence`` becomes a plain document, and inventing a second shape here would
give the system two encodings of the same fact that could drift apart under
maintenance. What this module adds on top is the thing the store does not
need: **strict decoding of input nobody here wrote**. The store decodes rows it
wrote itself, so a ``KeyError`` there is a bug; ingest decodes rows a remote
process wrote, where a missing key is Tuesday and must become a 4xx rather
than a traceback.

**The batch envelope carries ``signed_at`` inside the signed payload**, not
beside it in a header. Freshness is only worth checking if the timestamp
cannot be edited by whoever captured the bytes, and a header sits outside the
MAC (see :mod:`deadman.ingest.auth`).

**Serialisation is canonical** — sorted keys, no incidental whitespace —
because the signature covers the bytes. A serialiser whose output depended on
dict insertion order would make a correctly signed batch fail verification
based on how the collector happened to build its payload, which is the worst
class of bug: intermittent, environment-dependent, and indistinguishable from
an attack.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from deadman.evidence.model import Evidence, Method, Observation
from deadman.store.base import encode, instant

#: Bumped when the shape below changes incompatibly. A collector and a service
#: that disagree fail loudly at the version check rather than subtly at a field.
WIRE_VERSION = 1

#: Most rows one batch may carry. A collector sweeps a handful of surfaces, so
#: this is orders of magnitude above any honest payload; it exists so a body
#: that fits the byte cap cannot still cost an unbounded number of writes.
MAX_ROWS = 500

#: Most *distinct* surfaces one batch may name. The replay check reads back a
#: bounded slice of history per distinct surface, so rows alone do not bound
#: the cost of a request: 500 rows across 500 surfaces is 500 history queries.
#: A real collector sweeps a handful, and repeated readings of the same surface
#: are still free under :data:`MAX_ROWS`.
MAX_SURFACES = 50

#: How far ahead of this service's clock a collector's ``read_at`` may sit.
#: Real clocks disagree by seconds; a reading from the future is not a reading.
#: Without this, a forward-skewed row is judged fresh forever and also sorts
#: newest forever — the staleness detection this project exists to build,
#: disarmed by accident. See ``verify.collector_liveness._judge_surface``,
#: which refuses the same shape again for rows stored before this guard.
MAX_READ_AT_SKEW_SECONDS = 300.0

#: Longest a free-text row field may be. Well above any honest summary, and far
#: below the body cap, so one row cannot fill a batch with prose that then
#: lands on the public board.
MAX_TEXT_FIELD = 2000

#: Longest a surface id may be, and the shape it must take. Firestore rejects
#: ``""``, ``"."``, ``".."``, ``"__x__"`` and slashes as document ids, so an
#: unvalidated surface is an exception at ``append`` — a 500 reached *after*
#: the request was already authenticated and answered as acceptable.
#: ``/`` is allowed because surface ids genuinely contain it (``host:mac/disk``)
#: and ``store.base.surface_key`` percent-encodes before it reaches Firestore.
#: What is refused is what stays unusable after that encoding, plus anything
#: carrying whitespace or control characters into a document id.
MAX_SURFACE_LENGTH = 200
_SURFACE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]*$")
_RESERVED_SURFACES = frozenset({".", ".."})
_RESERVED_SURFACE_PATTERN = re.compile(r"^__.*__$")

#: Detail keys this service writes about a row, which a collector therefore may
#: not supply. Stripped from every incoming row rather than merely overwritten,
#: so downstream code can treat their presence as proof the service put them
#: there — which is what lets ``arrival.on_arrival`` safely preserve them on a
#: second annotation instead of laundering the original claim.
#:
#: A client-chosen ``wire_row_id`` is the sharp one: it is the dedupe identity,
#: so choosing it to collide with a row already inside the replay lookback
#: makes the service silently drop the new row and report the loss as
#: ``stored: 0``. Evidence loss, selected by whoever sent the evidence.
SERVICE_OWNED_DETAIL_KEYS = frozenset(
    {"collector_id", "received_at", "wire_row_id", "reported_method"}
)

_REQUIRED_ROW_FIELDS = ("surface", "observation", "method", "summary", "source", "read_at")


class WireError(ValueError):
    """The bytes are not a batch this service can read.

    Always a statement about the *request*, never about the service, which is
    what makes it safe for the endpoint to map straight onto a 4xx.
    """


@dataclass(frozen=True)
class Batch:
    """One collector's spool: who sent it, when they signed it, what they saw."""

    collector_id: str
    signed_at: datetime
    rows: tuple[Evidence, ...]


def encode_batch(batch: Batch) -> dict[str, Any]:
    """The batch as a plain JSON-ready document."""
    return {
        "version": WIRE_VERSION,
        "collector_id": batch.collector_id,
        "signed_at": instant(batch.signed_at).isoformat(),
        "rows": [encode(row) for row in batch.rows],
    }


def dumps(batch: Batch) -> bytes:
    """The exact bytes a collector signs and sends."""
    return json.dumps(encode_batch(batch), sort_keys=True, separators=(",", ":")).encode("utf-8")


def loads(raw: bytes, now: datetime | None = None) -> Batch:
    """Parse and validate bytes from a collector. Raises :class:`WireError`."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WireError(f"body is not valid JSON: {exc}") from exc
    return decode_batch(payload, now=now)


def decode_batch(payload: Any, now: datetime | None = None) -> Batch:
    """Validate an already-parsed payload into a :class:`Batch`."""
    if not isinstance(payload, Mapping):
        raise WireError("batch must be a JSON object")
    version = payload.get("version")
    if version != WIRE_VERSION:
        raise WireError(f"unsupported wire version {version!r}, this service speaks {WIRE_VERSION}")

    collector_id = payload.get("collector_id")
    if not isinstance(collector_id, str) or not collector_id.strip():
        raise WireError("collector_id must be a non-empty string")

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise WireError("rows must be a non-empty array")
    if len(rows) > MAX_ROWS:
        raise WireError(f"batch carries {len(rows)} rows, the cap is {MAX_ROWS}")

    decoded = tuple(decode_row(row, now=now) for row in rows)
    distinct = {row.surface for row in decoded}
    if len(distinct) > MAX_SURFACES:
        raise WireError(f"batch names {len(distinct)} distinct surfaces, the cap is {MAX_SURFACES}")

    return Batch(
        collector_id=collector_id,
        signed_at=_timestamp(payload.get("signed_at"), "signed_at"),
        rows=decoded,
    )


def decode_row(row: Any, now: datetime | None = None) -> Evidence:
    """One evidence row from untrusted input.

    Unknown enum values are refused rather than coerced. Defaulting an
    unrecognised method to the weakest tier would look conservative and would
    in fact be the opposite: it silently re-grades a claim whose grade the
    service did not understand, hiding a version skew that should be loud.
    """
    if not isinstance(row, Mapping):
        raise WireError("each row must be a JSON object")
    for name in _REQUIRED_ROW_FIELDS:
        if name not in row:
            raise WireError(f"row is missing required field {name!r}")
    for name in ("surface", "summary", "source"):
        if not isinstance(row[name], str):
            raise WireError(f"row field {name!r} must be a string")
    for name in ("summary", "source"):
        if len(row[name]) > MAX_TEXT_FIELD:
            raise WireError(
                f"row field {name!r} is {len(row[name])} chars, the cap is {MAX_TEXT_FIELD}"
            )

    detail = row.get("detail")
    if detail is None:
        detail = {}
    if not isinstance(detail, Mapping):
        raise WireError("row field 'detail' must be a JSON object")
    detail = {k: v for k, v in detail.items() if k not in SERVICE_OWNED_DETAIL_KEYS}

    return Evidence(
        surface=_surface(row["surface"]),
        observation=_member(Observation, row["observation"], "observation"),
        method=_member(Method, row["method"], "method"),
        summary=row["summary"],
        source=row["source"],
        read_at=_read_at(row["read_at"], now),
        detail=dict(detail),
    )


def _surface(value: str) -> str:
    """A surface id this service can actually store under.

    Refused here rather than at ``append`` because by then the request has been
    authenticated and implicitly accepted: the caller would see a 500 for input
    that was always unusable.
    """
    if len(value) > MAX_SURFACE_LENGTH:
        raise WireError(f"surface is {len(value)} chars, the cap is {MAX_SURFACE_LENGTH}")
    if (
        value in _RESERVED_SURFACES
        or _RESERVED_SURFACE_PATTERN.match(value)
        or not _SURFACE_PATTERN.match(value)
    ):
        raise WireError(f"surface {value!r} is not a usable id")
    return value


def _read_at(value: Any, now: datetime | None) -> datetime:
    """The collector's reading time, refused if it is implausibly ahead of ours.

    A reading from the future is not a reading. Left unchecked it is judged
    fresh forever (its age is negative, so it never exceeds any window) and it
    also sorts newest forever, which disarms staleness detection for that
    surface permanently.
    """
    read_at = _timestamp(value, "read_at")
    moment = instant(now) if now is not None else datetime.now(timezone.utc)
    ahead = (read_at - moment).total_seconds()
    if ahead > MAX_READ_AT_SKEW_SECONDS:
        raise WireError(
            f"read_at is {int(ahead)}s ahead of this service's clock, the allowed "
            f"skew is {MAX_READ_AT_SKEW_SECONDS:g}s"
        )
    return read_at


def _member(enum: type, value: Any, name: str) -> Any:
    try:
        return enum(value)
    except ValueError as exc:
        raise WireError(f"{name} {value!r} is not one of {[m.value for m in enum]}") from exc


def _timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise WireError(f"{name} must be an ISO 8601 string")
    try:
        return instant(datetime.fromisoformat(value))
    except ValueError as exc:
        raise WireError(f"{name} {value!r} is not an ISO 8601 timestamp") from exc
