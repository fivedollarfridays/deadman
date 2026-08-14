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

        try:
            record = json.loads(self.heartbeat_path.read_text())
        except OSError as exc:
            return unobservable(self.surface_id, src, f"cannot read heartbeat: {exc}")
        except ValueError as exc:
            return unobservable(self.surface_id, src, f"heartbeat is not valid JSON: {exc}")

        if not isinstance(record, dict):
            return unobservable(self.surface_id, src, "heartbeat is not a JSON object")

        last = self._parse_timestamp(record.get(self.timestamp_key))
        if last is None:
            return unobservable(
                self.surface_id,
                src,
                f"heartbeat has no parseable {self.timestamp_key!r} timestamp",
                keys=sorted(record),
            )

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
        for key, value in record.items():
            if key != self.timestamp_key:
                detail.setdefault(key, value)

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
