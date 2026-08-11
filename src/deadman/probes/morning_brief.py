"""Morning brief probe.

The control surface. This one already emits real capture evidence, so it
tests the probe interface rather than inventing an evidence source at the
same time. If the contract does not feel right here, it will not survive
Metricool.

**What counts as alive.** Not "the launchd job is loaded" and not "the script
exited zero". A brief is alive when a brief was *sent*, and the only thing
that proves that is a row written after a verified send. The job can run
daily, exit clean, and deliver nothing: that exact failure ran for nine days
undetected, and the reason nobody noticed is that the brief is itself the
alerting channel. A dead brief cannot report its own death.

**Why mtime is not the timestamp.** The obvious implementation reads the
log file's modification time. Do not. Any git checkout, any rsync, any
backup restore rewrites mtime and the file looks freshly written while its
contents are weeks stale. That is not hypothetical: a sibling system's
freshness check measured mtime, a routine checkout reset it, and the check
went green with nothing having regenerated. **Read the timestamp inside the
last row.** The file's metadata is not evidence about the file's contents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from deadman.evidence.model import Evidence, Method, Observation, unobservable

SURFACE = "cron:morning-brief"

#: 24h cadence plus 6h of slack. Tight enough to catch a single miss, loose
#: enough that a late run is not an incident.
DEFAULT_WINDOW_HOURS = 30.0


@dataclass(frozen=True)
class MorningBriefProbe:
    """Reads the send log and asks when a brief was last actually delivered."""

    log_path: Path
    window_hours: float = DEFAULT_WINDOW_HOURS

    @property
    def surface(self) -> str:
        return SURFACE

    @property
    def question(self) -> str:
        return f"was a morning brief verifiably sent within the last {self.window_hours:g}h?"

    def observe(self) -> Evidence:
        src = str(self.log_path)

        if not self.log_path.exists():
            return self._missing_log_result(src)

        try:
            rows = [ln for ln in self.log_path.read_text().splitlines() if ln.strip()]
        except OSError as exc:
            return unobservable(SURFACE, src, f"cannot read log: {exc}")

        if not rows:
            return self._fault(
                "send log is empty: no brief has ever been verifiably sent",
                src,
                last_send_at=None,
                age_hours=None,
                row_count=0,
            )

        last_send = self._parse_last_timestamp(rows)
        if last_send is None:
            # A corrupted tail tells us nothing about the brief. It tells us
            # our instrument is broken, which is a different sentence.
            return unobservable(
                SURFACE,
                src,
                "last log row has no parseable timestamp",
                row_count=len(rows),
                last_row=rows[-1][:200],
            )

        return self._age_result(last_send, len(rows), src)

    def _missing_log_result(self, src: str) -> Evidence:
        # Distinguish "the rail never produced evidence" from "we were
        # pointed somewhere that does not exist". A missing log inside a
        # directory that exists is a real finding. A missing directory is
        # a configuration problem, and calling that a fault would be
        # blaming the brief for our own bad path.
        if self.log_path.parent.is_dir():
            return self._fault(
                "send log absent: no brief has ever been verifiably sent",
                src,
                last_send_at=None,
                age_hours=None,
            )
        return unobservable(
            SURFACE,
            src,
            "log directory does not exist (path misconfigured?)",
            path=src,
        )

    def _age_result(self, last_send: datetime, row_count: int, src: str) -> Evidence:
        now = datetime.now(timezone.utc)
        age_h = (now - last_send).total_seconds() / 3600.0

        if age_h < -0.25:
            # Future-dated. Either clock skew or a hand-edited log; either way
            # the evidence is not trustworthy, so we do not rule on it.
            return unobservable(
                SURFACE,
                src,
                f"last send is {abs(age_h):.1f}h in the future (clock skew?)",
                last_send_at=last_send.isoformat(),
                row_count=row_count,
            )

        detail = {
            "last_send_at": last_send.isoformat(),
            "age_hours": round(age_h, 2),
            "window_hours": self.window_hours,
            "row_count": row_count,
        }

        if age_h > self.window_hours:
            missed = int(age_h // 24)
            return self._fault(
                f"no brief sent in {age_h:.1f}h (window {self.window_hours:g}h, ~{missed} missed)",
                src,
                **detail,
            )

        return Evidence(
            surface=SURFACE,
            observation=Observation.HEALTHY,
            method=Method.LOCAL_ARTIFACT,
            summary=f"brief sent {age_h:.1f}h ago",
            source=src,
            detail=detail,
        )

    @staticmethod
    def _parse_last_timestamp(rows: list[str]) -> datetime | None:
        """Timestamp from the newest row that yields one.

        Walks backwards rather than taking ``rows[-1]`` blindly: a crashed
        write can leave a torn final line, and one bad row should not blind
        us to a perfectly good one written the same day.
        """
        for line in reversed(rows):
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                continue
            raw = row.get("ts") or row.get("sent_at") or row.get("timestamp")
            if not isinstance(raw, str):
                continue
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return None

    @staticmethod
    def _fault(summary: str, source: str, **detail: object) -> Evidence:
        return Evidence(
            surface=SURFACE,
            observation=Observation.FAULT,
            method=Method.LOCAL_ARTIFACT,
            summary=summary,
            source=source,
            detail=dict(detail),
        )
