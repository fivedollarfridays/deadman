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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
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


def loads(raw: bytes) -> Batch:
    """Parse and validate bytes from a collector. Raises :class:`WireError`."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WireError(f"body is not valid JSON: {exc}") from exc
    return decode_batch(payload)


def decode_batch(payload: Any) -> Batch:
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

    return Batch(
        collector_id=collector_id,
        signed_at=_timestamp(payload.get("signed_at"), "signed_at"),
        rows=tuple(decode_row(row) for row in rows),
    )


def decode_row(row: Any) -> Evidence:
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

    detail = row.get("detail")
    if detail is None:
        detail = {}
    if not isinstance(detail, Mapping):
        raise WireError("row field 'detail' must be a JSON object")

    return Evidence(
        surface=row["surface"],
        observation=_member(Observation, row["observation"], "observation"),
        method=_member(Method, row["method"], "method"),
        summary=row["summary"],
        source=row["source"],
        read_at=_timestamp(row["read_at"], "read_at"),
        detail=dict(detail),
    )


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
