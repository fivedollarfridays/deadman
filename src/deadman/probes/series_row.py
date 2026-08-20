"""Series-row probe: did today's row get written?

Some trackers do not keep a heartbeat — they keep a *series*, one row per
day, and their correct failure mode is writing no row at all rather than a
zero (unknown-never-zero). kai-studio's devpost registration tracker is the
case this was built for: the fwtx-dao contract's headline metric, whose
scrape failure must never be recorded as "0 registrations".

``json_heartbeat`` cannot read that artifact, because absence *is* the
signal and there is no ``last_success`` field to age. Before this probe
existed the gap was papered over with an adapter in another repo that
translated "today's row exists" into a heartbeat file — a workaround whose
existence was the argument for this module.

**Local calendar days, not UTC.** Rows are stamped in the operator's
timezone. A probe asking for "today" in UTC starts demanding tomorrow's row
in the early local evening and would fault every night; a monitor that
alarms nightly is a monitor that gets muted.

Verdicts follow the house rules: a missing row inside a directory that
exists is a FAULT (the tracker did not run); a missing directory, an
unreadable file, or a shape we do not understand is UNOBSERVABLE (our
instrument is blind, which is a different sentence).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from deadman.evidence.model import Evidence, Method, Observation, unobservable

#: Same bounding doctrine as json_heartbeat: this artifact is written by a
#: process we do not control, and the ingest endpoint size-caps batches.
_MAX_EXTRA_KEYS = 10
_MAX_EXTRA_STR = 300


def _bounded_row(row: dict) -> dict[str, object]:
    out: dict[str, object] = {}
    for key in sorted(row)[:_MAX_EXTRA_KEYS]:
        value = row[key]
        if isinstance(value, str):
            out[str(key)[:100]] = value[:_MAX_EXTRA_STR]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[str(key)[:100]] = value
        else:
            out[str(key)[:100]] = f"<{type(value).__name__} len={len(value)}>"
    return out


@dataclass(frozen=True)
class SeriesRowProbe:
    """Asks whether a daily series carries a row for the current local day."""

    series_path: Path
    surface_id: str
    timezone_name: str = "America/Chicago"
    date_key: str = "date"

    @property
    def surface(self) -> str:
        return self.surface_id

    @property
    def question(self) -> str:
        return f"does {self.series_path.name} carry a row for today ({self.timezone_name})?"

    def observe(self) -> Evidence:
        src = str(self.series_path)

        try:
            today = datetime.now(ZoneInfo(self.timezone_name)).date().isoformat()
        except Exception as exc:  # noqa: BLE001 — bad tz config is our fault
            return unobservable(
                self.surface_id, src, f"unusable timezone {self.timezone_name!r}: {exc}"
            )

        if not self.series_path.exists():
            if self.series_path.parent.is_dir():
                return self._fault(
                    f"series file absent: the tracker has never written a row (expected {today})",
                    src,
                    expected_date=today,
                )
            return unobservable(
                self.surface_id,
                src,
                "series directory does not exist (path misconfigured?)",
                path=src,
            )

        try:
            rows = json.loads(self.series_path.read_text())
        except OSError as exc:
            return unobservable(self.surface_id, src, f"cannot read series: {exc}")
        except ValueError as exc:
            return unobservable(self.surface_id, src, f"series is not valid JSON: {exc}")

        if not isinstance(rows, list):
            return unobservable(self.surface_id, src, "series is not a JSON array of rows")

        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get(self.date_key) == today:
                return Evidence(
                    surface=self.surface_id,
                    observation=Observation.HEALTHY,
                    method=Method.LOCAL_ARTIFACT,
                    summary=f"series carries today's row ({today})",
                    source=src,
                    detail=_bounded_row(row),
                )

        latest = None
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get(self.date_key), str):
                value = row[self.date_key]
                latest = value if latest is None or value > latest else latest
        return self._fault(
            f"no row for today ({today}) — the tracker did not run"
            + (f"; newest row is {latest}" if latest else "; series is empty"),
            src,
            expected_date=today,
            newest_row=latest,
            rows=len(rows),
        )

    def _fault(self, summary: str, src: str, **detail: object) -> Evidence:
        return Evidence(
            surface=self.surface_id,
            observation=Observation.FAULT,
            method=Method.LOCAL_ARTIFACT,
            summary=summary,
            source=src,
            detail=dict(detail),
        )
