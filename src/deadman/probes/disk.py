"""Disk probe.

**Rate, not threshold.** A level check is why this surface is in the set. The
volume never crossed a line and got caught; it drifted for weeks and then hit
a wall on a deadline morning, taking a container runtime's blob store with it
and destroying a demo environment three hours before a submission. At any
point in those weeks a threshold check would have said "fine". A slope would
have said "you have nine days".

So a healthy level with a bad trend is a **fault**, not a pass. That is the
entire argument of this probe and it is the thing threshold monitoring
structurally cannot express.

**This probe records in order to observe.** Every other surface here reads
evidence somebody else produced. A trend has no artifact until you make one,
so ``observe()`` appends the current reading to a history file and then
reasons over the series. That is a side effect inside a probe, done knowingly:
you cannot measure a rate from a single sample, and refusing to accumulate
would mean refusing to answer the only question that matters.

**One machine's disk says nothing about another's.** ``host`` exists so the
same probe, pointed at two different machines' volumes, produces two
surface ids that cannot collide even when both mount their primary volume
at ``/`` — see ``host:mac/disk`` and ``host:rig/disk`` in
``docs/surfaces.md``. Blank preserves the original single-machine id.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from deadman.evidence.model import Evidence, Method, Observation, unobservable

GB = 1024**3

#: Absolute, not proportional. "How much room do I need to work" does not
#: scale with volume size: 3% of 4TB is roomy, 3% of 128GB is a crisis.
DEFAULT_FLOOR_BYTES = 5 * GB

#: Fire while there is still time to act. Nine days of warning is useless if
#: the alarm waits until day nine.
DEFAULT_RUNWAY_DAYS = 14.0

DEFAULT_WINDOW_DAYS = 21.0


@dataclass(frozen=True)
class DiskProbe:
    volume: Path = Path("/")
    history_path: Path = Path("disk-history.jsonl")
    #: Which machine this volume lives on, e.g. ``"mac"`` or ``"rig"``. Blank
    #: preserves the original single-machine id. A full Mac disk says
    #: nothing about the rig's, so the two need surface ids that cannot
    #: collide even when both mount their primary volume at ``/`` — that is
    #: the entire reason this field exists rather than reusing ``volume``.
    host: str = ""
    floor_bytes: int = DEFAULT_FLOOR_BYTES
    runway_days: float = DEFAULT_RUNWAY_DAYS
    window_days: float = DEFAULT_WINDOW_DAYS

    @property
    def surface(self) -> str:
        if not self.host:
            return f"host:disk{self.volume}"
        volume_str = str(self.volume)
        suffix = "" if volume_str == "/" else volume_str
        return f"host:{self.host}/disk{suffix}"

    @property
    def question(self) -> str:
        return (
            f"is {self.volume} above {self.floor_bytes / GB:.0f}GB, and does the "
            f"trend keep it there for {self.runway_days:g} days?"
        )

    def observe(self) -> Evidence:
        src = f"statvfs:{self.volume}"
        try:
            usage = shutil.disk_usage(self.volume)
        except OSError as exc:
            return unobservable(
                self.surface, src, f"cannot stat volume: {exc}", path=str(self.volume)
            )

        now = datetime.now(timezone.utc)
        free = usage.free
        self._record(now, free)
        series = self._load_window(now)

        free_gb = free / GB
        detail: dict[str, object] = {
            "free_bytes": free,
            "free_gb": round(free_gb, 2),
            "total_gb": round(usage.total / GB, 2),
            "pct_free": round(100 * free / usage.total, 2),
            "floor_gb": round(self.floor_bytes / GB, 2),
            "samples": len(series),
        }

        # Already below the floor. No projection needed and none is useful.
        if free <= self.floor_bytes:
            return self._fault(
                f"{free_gb:.1f}GB free, at or below the {self.floor_bytes / GB:.0f}GB floor",
                src,
                **detail,
            )

        return self._trend_result(free, free_gb, series, src, detail)

    def _trend_result(
        self,
        free: int,
        free_gb: float,
        series: list[tuple[datetime, int]],
        src: str,
        detail: dict[str, object],
    ) -> Evidence:
        slope = _bytes_per_day(series)
        if slope is None:
            # One sample is a level, not a trend. Say so rather than implying
            # a projection exists.
            detail["trend"] = "insufficient history"
            return Evidence(
                surface=self.surface,
                observation=Observation.HEALTHY,
                method=Method.LOCAL_ARTIFACT,
                summary=f"{free_gb:.1f}GB free (no trend yet, {len(series)} sample(s))",
                source=src,
                detail=detail,
            )

        detail["slope_gb_per_day"] = round(slope / GB, 3)

        # Slope is change in free bytes per day. Negative means filling.
        if slope >= 0:
            detail["runway_days"] = None
            return Evidence(
                surface=self.surface,
                observation=Observation.HEALTHY,
                method=Method.LOCAL_ARTIFACT,
                summary=f"{free_gb:.1f}GB free, not shrinking",
                source=src,
                detail=detail,
            )

        runway = (free - self.floor_bytes) / -slope
        detail["runway_days"] = round(runway, 1)

        if runway <= self.runway_days:
            return self._fault(
                f"{free_gb:.1f}GB free but losing {-slope / GB:.2f}GB/day: "
                f"hits the floor in {runway:.1f} days",
                src,
                **detail,
            )

        return Evidence(
            surface=self.surface,
            observation=Observation.HEALTHY,
            method=Method.LOCAL_ARTIFACT,
            summary=f"{free_gb:.1f}GB free, {runway:.0f} days of runway",
            source=src,
            detail=detail,
        )

    def _record(self, when: datetime, free: int) -> None:
        """Append one sample. Best effort: failing to extend the history must
        never prevent reporting the level we already measured."""
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("a") as fh:
                fh.write(json.dumps({"ts": when.isoformat(), "free": free}) + "\n")
        except OSError:
            pass

    def _load_window(self, now: datetime) -> list[tuple[datetime, int]]:
        cutoff = now - timedelta(days=self.window_days)
        out: list[tuple[datetime, int]] = []
        try:
            lines = self.history_path.read_text().splitlines()
        except OSError:
            return out
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                ts = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00"))
                free = int(row["free"])
            except (ValueError, TypeError, KeyError):
                continue  # a torn row loses one sample, not the series
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                out.append((ts, free))
        return sorted(out)

    def _fault(self, summary: str, source: str, **detail: object) -> Evidence:
        return Evidence(
            surface=self.surface,
            observation=Observation.FAULT,
            method=Method.LOCAL_ARTIFACT,
            summary=summary,
            source=source,
            detail=dict(detail),
        )


def _bytes_per_day(series: list[tuple[datetime, int]]) -> float | None:
    """Least-squares slope in bytes/day, or None with fewer than two samples.

    Least squares rather than first-versus-last because a single noisy
    reading, a big temp file mid-build, should not swing the projection.
    """
    if len(series) < 2:
        return None
    t0 = series[0][0]
    xs = [(ts - t0).total_seconds() / 86400.0 for ts, _ in series]
    ys = [float(free) for _, free in series]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:  # every sample at the same instant
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
