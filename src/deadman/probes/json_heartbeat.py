"""Generic JSON-heartbeat probe.

Several rails in the estate already write a success heartbeat in one shared
shape — a JSON file whose ``last_success`` field is stamped only after the
rail's work actually completed (the ops comms-freshness contract). This probe
makes any of them a deadman surface by config alone: the surface id, the
file, and the window are arguments, not code.

Same rules as every capture probe here: the timestamp is read from *inside*
the record (mtime is rewritten by checkouts and restores, and must never
count), a heartbeat that has never been written inside an existing directory
is a FAULT, and a record we cannot read or parse is UNOBSERVABLE — our
instrument is blind, which is a different sentence from "the rail is dead".

The record's other fields (counts, skipped rows, whatever the rail chose to
report about its last run) ride along in the evidence detail, so downstream
interpretation sees what the run *did*, not merely that it happened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from deadman.evidence.model import Evidence, Method, Observation, unobservable

#: A heartbeat this far in the future is clock skew or a hand-edited file,
#: not evidence. Quarter of an hour of slack absorbs honest drift.
_FUTURE_SLACK_HOURS = 0.25

#: Caps on record extras carried into evidence detail. The heartbeat file is
#: written by another process this probe does not control; without bounds a
#: bloated or hostile record would ride verbatim into the evidence batch
#: (which the ingest endpoint size-caps, so an oversized detail would take
#: the whole sweep's delivery down with it).
_MAX_EXTRA_KEYS = 10
_MAX_EXTRA_STR = 300


#: Evidence's own field names. Extras are splatted as ``**detail`` into helpers
#: that already bind some of these as parameters, so a producer key of the same
#: name is a TypeError at the call site — not a bad value, a crash.
#:
#: DM3.1, found live: ``cron:devpost`` alerted five times on 2026-08-27 with
#: ``_fault() got multiple values for argument 'source'`` because its heartbeat
#: is ``{last_success, row, source}``. The probe was reporting REAL staleness
#: and raised on the way, so the board showed UNOBSERVABLE ("we cannot see it")
#: for something that was FAULT ("it is broken"). **The bug inverted the
#: diagnosis exactly when the monitor was load-bearing** — and because the
#: healthy path never splats detail, it stayed invisible until a surface failed.
#:
#: Namespaced rather than dropped: doctrine §5 is tolerate-drift-or-fail-loud,
#: never silently discard. The producer's value survives under ``hb_``.
_RESERVED_EVIDENCE_FIELDS = frozenset(
    {"surface", "observation", "method", "summary", "source", "detail"}
)
_EXTRA_PREFIX = "hb_"


def _safe_extra_key(key: str) -> str:
    """Namespace a producer key that would shadow an Evidence field."""
    return f"{_EXTRA_PREFIX}{key}" if key in _RESERVED_EVIDENCE_FIELDS else key


def _bounded_extras(record: dict, *, exclude: str) -> dict[str, object]:
    """Record extras, bounded: scalars only, strings truncated, key count
    capped, containers summarised by size rather than copied.

    Keys colliding with an Evidence field are namespaced (see
    ``_RESERVED_EVIDENCE_FIELDS``) so a producer can never crash its reader.
    """
    extras: dict[str, object] = {}
    for key in sorted(k for k in record if k != exclude)[:_MAX_EXTRA_KEYS]:
        value = record[key]
        safe = _safe_extra_key(str(key)[:100])
        if isinstance(value, str):
            extras[safe] = value[:_MAX_EXTRA_STR]
        elif isinstance(value, (int, float, bool)) or value is None:
            extras[safe] = value
        elif isinstance(value, (list, dict)):
            # Small containers (a counts dict, a short skip list) are the
            # useful case; big ones are summarised, never copied.
            as_json = json.dumps(value)
            extras[safe] = (
                value
                if len(as_json) <= _MAX_EXTRA_STR
                else f"<{type(value).__name__}, {len(value)} items>"
            )
    return extras


@dataclass(frozen=True)
class JsonHeartbeatProbe:
    """Reads a success-heartbeat record and asks how long ago the rail last
    verifiably did its job."""

    heartbeat_path: Path
    surface_id: str
    window_hours: float
    timestamp_key: str = "last_success"

    @property
    def surface(self) -> str:
        return self.surface_id

    @property
    def question(self) -> str:
        return (
            f"did the rail behind {self.heartbeat_path.name} succeed within "
            f"the last {self.window_hours:g}h?"
        )

    def observe(self) -> Evidence:
        src = str(self.heartbeat_path)

        if not self.heartbeat_path.exists():
            return self._missing_result(src)

        record = self._load_record(src)
        if isinstance(record, Evidence):  # already an UNOBSERVABLE verdict
            return record

        last = self._parse_timestamp(record.get(self.timestamp_key))
        if last is None:
            return unobservable(
                self.surface_id,
                src,
                f"heartbeat has no parseable {self.timestamp_key!r} timestamp",
                keys=sorted(record)[:_MAX_EXTRA_KEYS],
            )
        return self._age_result(record, last, src)

    def _missing_result(self, src: str) -> Evidence:
        # A heartbeat that was never written inside an existing directory is
        # a real finding; a missing directory is our own bad path.
        if self.heartbeat_path.parent.is_dir():
            return self._fault(
                "heartbeat absent: the rail has never recorded a success",
                src,
                last_success=None,
            )
        return unobservable(
            self.surface_id,
            src,
            "heartbeat directory does not exist (path misconfigured?)",
            path=src,
        )

    def _load_record(self, src: str) -> dict | Evidence:
        try:
            record = json.loads(self.heartbeat_path.read_text())
        except OSError as exc:
            return unobservable(self.surface_id, src, f"cannot read heartbeat: {exc}")
        except ValueError as exc:
            return unobservable(self.surface_id, src, f"heartbeat is not valid JSON: {exc}")
        if not isinstance(record, dict):
            return unobservable(self.surface_id, src, "heartbeat is not a JSON object")
        return record

    def _age_result(self, record: dict, last: datetime, src: str) -> Evidence:
        now = datetime.now(timezone.utc)
        age_h = (now - last).total_seconds() / 3600.0

        if age_h < -_FUTURE_SLACK_HOURS:
            return unobservable(
                self.surface_id,
                src,
                f"last success is {abs(age_h):.1f}h in the future (clock skew?)",
                last_success=last.isoformat(),
            )

        detail: dict[str, object] = {
            "last_success": last.isoformat(),
            "age_hours": round(age_h, 2),
            "window_hours": self.window_hours,
        }
        detail.update(_bounded_extras(record, exclude=self.timestamp_key))

        if age_h > self.window_hours:
            return self._fault(
                f"no successful run in {age_h:.1f}h (window {self.window_hours:g}h)",
                src,
                **detail,
            )

        return Evidence(
            surface=self.surface_id,
            observation=Observation.HEALTHY,
            method=Method.LOCAL_ARTIFACT,
            summary=f"last success {age_h:.1f}h ago",
            source=src,
            detail=detail,
        )

    @staticmethod
    def _parse_timestamp(raw: object) -> datetime | None:
        if not isinstance(raw, str):
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _fault(self, summary: str, source: str, **detail: object) -> Evidence:
        return Evidence(
            surface=self.surface_id,
            observation=Observation.FAULT,
            method=Method.LOCAL_ARTIFACT,
            summary=summary,
            source=source,
            detail=dict(detail),
        )
