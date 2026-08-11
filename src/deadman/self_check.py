"""Does deadman itself still run, and can it prove it.

Every other module in this package watches something else. This one watches
the watcher, and it is the module the whole project is least entitled to get
wrong: a monitor that fails silently is worse than no monitor, because it
occupies the place where a working one would go.

**Liveness is proved from capture evidence, never from a heartbeat.** The rule
this codebase applies to every other surface applies hardest here. "The
process started" and "the timer is loaded" are claims about intent. The only
acceptable evidence that a sweep happened is a row written *after* a sweep
completed, by the code that completed it.

**The timestamp lives inside the row, not on the file.** Same reason as
:mod:`deadman.probes.morning_brief`: a checkout, an rsync or a backup restore
rewrites mtime, and a freshness check reading file metadata goes green with
nothing having run. That is not hypothetical, it happened to a sibling system.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from deadman.remediate.alert import AlertChannel

#: A daily sweep plus six hours of slack. Tight enough to catch a single
#: missed run, loose enough that a late one is not an incident.
DEFAULT_WINDOW_HOURS = 30.0


class Liveness(str, Enum):
    """Three states, for the same reason :class:`Observation` has three."""

    LIVE = "live"
    """A sweep completed inside the window and wrote a row saying so."""

    STALE = "stale"
    """Evidence exists but is too old. deadman ran once and has stopped."""

    NO_EVIDENCE = "no_evidence"
    """Nothing has ever been written, or the log cannot be read.

    Deliberately distinct from ``STALE``. "It stopped" and "it never started,
    or we are looking in the wrong place" call for different actions, and
    collapsing them costs whoever is woken up their first ten minutes.
    """


@dataclass(frozen=True)
class SelfCheckResult:
    """The verdict, and the exit code that carries it to a scheduler."""

    liveness: Liveness
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        """0 only when live.

        Anything else is non-zero on purpose, including ``NO_EVIDENCE``. The
        temptation is to treat "no data" as "nothing to report" and exit clean,
        which is precisely how a monitor goes quiet without anyone noticing.
        No evidence is the loudest state there is.
        """
        return 0 if self.liveness is Liveness.LIVE else 1


@dataclass(frozen=True)
class SelfEvidenceLog:
    """The append-only record of sweeps that actually finished."""

    path: Path

    def record(self, *, sweep_size: int, blind: int, when: datetime | None = None) -> None:
        """Append one row. Call this only after a sweep has completed."""
        stamp = when or datetime.now(timezone.utc)
        row = {"ts": stamp.isoformat(), "sweep_size": sweep_size, "blind": blind}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")

    def latest(self) -> datetime | None:
        """Timestamp of the newest usable row, or ``None`` if there is none."""
        try:
            lines = self.path.read_text().splitlines()
        except OSError:
            return None

        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                parsed = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00"))
            except (ValueError, TypeError, KeyError):
                continue
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return None


def self_check(
    log: SelfEvidenceLog,
    window_hours: float = DEFAULT_WINDOW_HOURS,
    now: datetime | None = None,
) -> SelfCheckResult:
    """Has a sweep completed recently enough, according to what it wrote."""
    moment = now or datetime.now(timezone.utc)
    last = log.latest()

    if last is None:
        return SelfCheckResult(
            liveness=Liveness.NO_EVIDENCE,
            summary=f"no completed sweep has ever been recorded at {log.path}",
            detail={"log_path": str(log.path), "window_hours": window_hours},
        )

    age_h = (moment - last).total_seconds() / 3600.0
    detail = {
        "log_path": str(log.path),
        "last_sweep_at": last.isoformat(),
        "age_hours": round(age_h, 2),
        "window_hours": window_hours,
    }

    if age_h > window_hours:
        return SelfCheckResult(
            liveness=Liveness.STALE,
            summary=(
                f"last completed sweep was {age_h:.1f}h ago, outside the {window_hours:g}h window"
            ),
            detail=detail,
        )

    return SelfCheckResult(
        liveness=Liveness.LIVE,
        summary=f"last completed sweep was {age_h:.1f}h ago",
        detail=detail,
    )


def run_self_check(
    log: SelfEvidenceLog,
    window_hours: float = DEFAULT_WINDOW_HOURS,
    channel: AlertChannel | None = None,
    now: datetime | None = None,
) -> SelfCheckResult:
    """Check, and raise the alarm out of band if the answer is bad.

    The alarm is deliberately not sent through anything deadman watches; see
    :mod:`deadman.remediate.alert`, which enforces that at construction. This
    function only has to decide *whether* to shout.
    """
    result = self_check(log, window_hours=window_hours, now=now)
    if channel is not None and result.liveness is not Liveness.LIVE:
        channel.alert(f"deadman self-check {result.liveness.value}: {result.summary}")
    return result


def main(argv: list[str] | None = None) -> int:
    """Entry point for a scheduler. The exit code is the whole interface."""
    parser = argparse.ArgumentParser(prog="deadman-self-check", description=__doc__)
    parser.add_argument(
        "--log",
        default=os.environ.get("DEADMAN_SELF_LOG", "/tmp/deadman/self-evidence.jsonl"),
        help="path to the self-evidence log written by completed sweeps",
    )
    parser.add_argument("--window-hours", type=float, default=DEFAULT_WINDOW_HOURS)
    args = parser.parse_args(argv)

    result = run_self_check(SelfEvidenceLog(path=Path(args.log)), window_hours=args.window_hours)
    print(f"{result.liveness.value}: {result.summary}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
