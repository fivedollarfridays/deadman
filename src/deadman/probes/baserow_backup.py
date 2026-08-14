"""Baserow backup probe: the artifact is the evidence.

The HackFW Baserow stack backs up nightly into the ``baserow_backups``
volume, and the failure mode this probe exists for is not a red cron — it is
a crontab line that runs *nothing* and logs *nowhere* while looking
installed. That exact failure shipped: the backup cron pointed at a deleted
engage worktree for two days, exit status invisible, log path equally dead.
A probe that read the cron's log would have been blind; a probe that lists
the volume is not.

The timestamp is encoded in the newest artifact's filename
(``baserow_backup_YYYYMMDD_HHMMSS.tar.gz``, stamped by ``infra/backup.sh``
in the machine's local time) — content, not mtime, same doctrine as every
capture probe here.

Docker unreachable, container down, or a listing with no parseable names is
UNOBSERVABLE: the instrument is blind (the stack watchdog owns "is the
container up"), and blaming the backups for our blindness would be the exact
laundering the probe contract forbids.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from deadman.evidence.model import Evidence, Method, Observation, unobservable

SURFACE = "backup:baserow"

#: Nightly cadence (03:00) plus slack: one missed night alarms the next.
DEFAULT_WINDOW_HOURS = 26.0

_NAME_RE = re.compile(r"baserow_backup_(\d{8})_(\d{6})\.tar\.gz$")

#: backup.sh stamps filenames with `date +%Y%m%d_%H%M%S` — machine-local time.
_LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo


def _default_run(argv: list[str]) -> tuple[int, str]:
    """(returncode, combined output). Errors escape to run_probe's containment."""
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout + proc.stderr


@dataclass(frozen=True)
class BaserowBackupProbe:
    """Lists the backup volume inside the container and asks how old the
    newest actual backup artifact is."""

    container: str = "infra-baserow-1"
    backups_dir: str = "/baserow/backups"
    window_hours: float = DEFAULT_WINDOW_HOURS
    docker_bin: str = "docker"
    run_cmd: Callable[[list[str]], tuple[int, str]] = field(default=_default_run)

    @property
    def surface(self) -> str:
        return SURFACE

    @property
    def question(self) -> str:
        return (
            f"does a Baserow backup artifact newer than {self.window_hours:g}h "
            f"exist in {self.container}:{self.backups_dir}?"
        )

    def observe(self) -> Evidence:
        src = f"{self.container}:{self.backups_dir}"
        argv = [
            self.docker_bin,
            "exec",
            self.container,
            "sh",
            "-c",
            f"ls -1 {self.backups_dir}",
        ]

        try:
            code, output = self.run_cmd(argv)
        except FileNotFoundError:
            return unobservable(SURFACE, src, f"{self.docker_bin!r} not found on PATH")
        except subprocess.TimeoutExpired:
            return unobservable(SURFACE, src, "docker exec timed out")

        if code != 0:
            return unobservable(
                SURFACE,
                src,
                f"cannot list backup volume (exit {code})",
                output=output.strip()[:300],
            )

        stamps = self._parse_listing(output)
        names = [n for n, _ in stamps]

        if not output.strip():
            return self._fault("backup volume is empty: no backup has ever been produced", src)
        if not stamps:
            return unobservable(
                SURFACE,
                src,
                "listing contains no parseable backup artifact names",
                listing=output.strip().splitlines()[:10],
            )

        newest_name, newest_at = max(stamps, key=lambda s: s[1])
        age_h = (datetime.now(timezone.utc) - newest_at).total_seconds() / 3600.0
        detail = {
            "newest": newest_name,
            "newest_at": newest_at.isoformat(),
            "age_hours": round(age_h, 2),
            "window_hours": self.window_hours,
            "backup_count": len(names),
        }

        if age_h > self.window_hours:
            return self._fault(
                f"newest backup is {age_h:.0f}h old (window {self.window_hours:g}h)",
                src,
                **detail,
            )

        return Evidence(
            surface=SURFACE,
            observation=Observation.HEALTHY,
            method=Method.LOCAL_ARTIFACT,
            summary=f"backup {age_h:.1f}h old ({len(names)} retained)",
            source=src,
            detail=detail,
        )

    @staticmethod
    def _parse_listing(output: str) -> list[tuple[str, datetime]]:
        stamps: list[tuple[str, datetime]] = []
        for line in output.splitlines():
            match = _NAME_RE.search(line.strip())
            if not match:
                continue
            try:
                naive = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
            except ValueError:
                continue
            stamps.append((line.strip(), naive.replace(tzinfo=_LOCAL_TZ).astimezone(timezone.utc)))
        return stamps

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
