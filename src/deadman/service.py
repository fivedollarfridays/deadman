"""The Cloud Run service: publishes the current board.

A plain WSGI callable, no framework. The package declares zero runtime
dependencies (see ``pyproject.toml``); pulling in a web framework for one
JSON endpoint would trade that for nothing. ``wsgiref`` (stdlib) serves it.

The board itself is exactly ``sweep()`` plus ``blind_spots()`` over whatever
probes need no secrets to run — see ``deadman.probes.base``. Only surfaces
that need no credentials are wired in here; a probe that raised or returned
nonsense is not an outage in this endpoint, it is another row on the board,
which is the entire point of the never-raise contract it is built on.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from wsgiref.simple_server import make_server

from deadman.evidence.model import Evidence, Observation
from deadman.probes.base import Probe, blind_spots, sweep
from deadman.probes.disk import DiskProbe
from deadman.probes.morning_brief import MorningBriefProbe
from deadman.self_check import SelfEvidenceLog

ProbesFn = Callable[[], list[Probe]]


def default_probes() -> list[Probe]:
    """Probes safe to run anywhere, Cloud Run included: no credentials, no
    outbound network. Everything else (Metricool, destinations, SMS relay)
    needs secrets this endpoint does not hold."""
    brief_log = Path(os.environ.get("DEADMAN_BRIEF_LOG", "/var/log/deadman/morning-brief.jsonl"))
    disk_history = Path(os.environ.get("DEADMAN_DISK_HISTORY", "/tmp/deadman/disk-history.jsonl"))
    return [
        DiskProbe(history_path=disk_history),
        MorningBriefProbe(log_path=brief_log),
    ]


def _evidence_row(evidence: Evidence) -> dict[str, object]:
    return {
        "surface": evidence.surface,
        "observation": evidence.observation.value,
        "method": evidence.method.value,
        "summary": evidence.summary,
        "source": evidence.source,
        "read_at": evidence.read_at.isoformat(),
        "detail": evidence.detail,
    }


def build_board(probes: list[Probe], self_log: SelfEvidenceLog | None = None) -> dict[str, object]:
    """The current board: every probe's evidence plus the counts a human
    reads first. Blind spots get their own field per ``base.blind_spots`` —
    a summary that folds them into "healthy" is the lie this project is
    about.

    When ``self_log`` is given, a row is appended *after* the sweep completes.
    That row is the only evidence deadman has that it is alive (see
    ``deadman.self_check``), and it is written here rather than at startup on
    purpose: what needs proving is that a sweep finished, not that a process
    began.
    """
    evidence = sweep(probes)
    blind = blind_spots(evidence)
    if self_log is not None:
        self_log.record(sweep_size=len(evidence), blind=len(blind))
    return {
        "surfaces": [_evidence_row(e) for e in evidence],
        "blind_spots": [e.surface for e in blind],
        "healthy_count": sum(1 for e in evidence if e.observation is Observation.HEALTHY),
        "fault_count": sum(1 for e in evidence if e.observation is Observation.FAULT),
        "blind_count": len(blind),
    }


def make_app(
    probes_fn: ProbesFn, self_log: SelfEvidenceLog | None = None
) -> Callable[[dict, Callable], Iterable[bytes]]:
    """Build a WSGI app reading probes from ``probes_fn`` on every request,
    so the board reflects the current state rather than one taken at
    startup.

    ``self_log`` is written only on a served board, never on a rejected
    request. A 405 is not a sweep, and recording it would let a stream of bad
    requests forge liveness for a service whose probes never ran.
    """

    def app(environ: dict, start_response: Callable) -> Iterable[bytes]:
        if environ.get("REQUEST_METHOD") != "GET":
            body = b'{"error": "method not allowed"}'
            start_response(
                "405 Method Not Allowed",
                [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
            )
            return [body]

        board = build_board(probes_fn(), self_log=self_log)
        body = json.dumps(board).encode("utf-8")
        start_response(
            "200 OK",
            [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
        )
        return [body]

    return app


def default_self_log() -> SelfEvidenceLog:
    """Where the deployed service records that a sweep finished.

    Cloud Run's filesystem is per-instance and ephemeral, so this proves the
    liveness of *an instance*, not of the service across cold starts. That is
    a real limitation and it is stated here rather than left to be discovered:
    a durable self-evidence store is what makes this claim survive scale-to-
    zero, and it is v2.
    """
    return SelfEvidenceLog(
        path=Path(os.environ.get("DEADMAN_SELF_LOG", "/tmp/deadman/self-evidence.jsonl"))
    )


app = make_app(default_probes, self_log=default_self_log())


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    with make_server("0.0.0.0", port, app) as httpd:  # noqa: S104 — Cloud Run requires binding all interfaces
        httpd.serve_forever()


if __name__ == "__main__":
    main()
