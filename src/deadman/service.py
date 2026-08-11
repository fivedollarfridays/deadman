"""The Cloud Run service: publishes the current board, and takes evidence in.

A plain WSGI callable, no framework. The package declares zero runtime
dependencies (see ``pyproject.toml``); pulling in a web framework for two
JSON endpoints would trade that for nothing. ``wsgiref`` (stdlib) serves it.

``GET /`` is the board: exactly ``sweep()`` plus ``blind_spots()`` over
whatever probes need no secrets to run — see ``deadman.probes.base``. Only
surfaces that need no credentials are wired in here; a probe that raised or
returned nonsense is not an outage in this endpoint, it is another row on the
board, which is the entire point of the never-raise contract it is built on.

``POST /evidence`` is how the surfaces that *do* need credentials — or that
live on a machine Cloud Run cannot reach at all — get onto that board. See
:mod:`deadman.ingest` for what changes about a claim when it crosses that
wire.

**This module refuses to import without an ingest secret.** ``app`` is built
at module scope and building it reads the environment, so an unconfigured
deploy dies at startup rather than serving an endpoint that would accept
evidence from anyone who can reach the URL.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from wsgiref.simple_server import make_server

from deadman.evidence.model import Evidence, Observation
from deadman.ingest.auth import secret_from_env
from deadman.ingest.endpoint import EVIDENCE_PATH, IngestEndpoint
from deadman.probes.base import Probe, blind_spots, sweep
from deadman.probes.disk import DiskProbe
from deadman.probes.morning_brief import MorningBriefProbe
from deadman.self_check import SelfEvidenceLog
from deadman.store.base import EvidenceStore
from deadman.store.firestore import FirestoreEvidenceStore
from deadman.store.memory import InMemoryEvidenceStore

ProbesFn = Callable[[], list[Probe]]

#: Which :mod:`deadman.store` backend the service writes ingested evidence to.
STORE_BACKEND_ENV = "DEADMAN_STORE_BACKEND"

#: GCP project for the Firestore backend. Unset means the SDK's own default.
FIRESTORE_PROJECT_ENV = "DEADMAN_FIRESTORE_PROJECT"


_METHOD_NOT_ALLOWED = "405 Method Not Allowed"


class StoreMisconfigured(RuntimeError):
    """The configured store backend is not one that exists."""


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


def _respond(start_response: Callable, status: str, payload: object) -> Iterable[bytes]:
    body = json.dumps(payload).encode("utf-8")
    start_response(
        status,
        [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
    )
    return [body]


def make_app(
    probes_fn: ProbesFn,
    self_log: SelfEvidenceLog | None = None,
    ingest: IngestEndpoint | None = None,
) -> Callable[[dict, Callable], Iterable[bytes]]:
    """Build a WSGI app reading probes from ``probes_fn`` on every request,
    so the board reflects the current state rather than one taken at
    startup.

    ``self_log`` is written only on a served board, never on a rejected
    request and never on an ingest. A 405 is not a sweep and neither is a
    delivered batch; recording either would let traffic forge liveness for a
    service whose probes never ran.

    ``ingest`` is optional so the board can be built and tested on its own.
    The deployed ``app`` below always passes one, and a request to
    ``/evidence`` without one is a 405 — an endpoint that is not wired says
    so, rather than accepting a batch and dropping it.
    """

    def app(environ: dict, start_response: Callable) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD")
        path = environ.get("PATH_INFO", "/")

        if path == EVIDENCE_PATH:
            if method != "POST" or ingest is None:
                return _respond(
                    start_response, _METHOD_NOT_ALLOWED, {"error": "method not allowed"}
                )
            status, payload = ingest.handle(environ)
            return _respond(start_response, status, payload)

        if method != "GET":
            return _respond(start_response, _METHOD_NOT_ALLOWED, {"error": "method not allowed"})

        return _respond(start_response, "200 OK", build_board(probes_fn(), self_log=self_log))

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


def default_store() -> EvidenceStore:
    """Where ingested evidence goes, chosen by ``DEADMAN_STORE_BACKEND``.

    Defaults to memory, which is correct for a local run and wrong for the
    deploy — Cloud Run's instances are ephemeral, so a memory-backed service
    forgets the estate on every scale-to-zero. ``cloudbuild.yaml`` therefore
    sets ``firestore`` explicitly, and an unrecognised name is a startup
    failure rather than a silent fallback to the forgetful backend.

    **The forgetful backend announces itself on stderr**, which Cloud Run
    captures. A deploy that missed the variable would otherwise answer a
    collector with ``stored: 1`` for evidence that dies at the next
    scale-to-zero — a false green of exactly the kind this project exists to
    catch, and one nobody would find by looking at the board.
    """
    name = os.environ.get(STORE_BACKEND_ENV, "memory").strip().lower()
    if name == "memory":
        print(
            f"deadman: storing evidence in memory ({STORE_BACKEND_ENV} is unset or 'memory'). "
            f"This instance will forget every row it is told when it restarts. "
            f"Set {STORE_BACKEND_ENV}=firestore for anything that must outlive a process.",
            file=sys.stderr,
        )
        return InMemoryEvidenceStore()
    if name == "firestore":
        return FirestoreEvidenceStore(project=os.environ.get(FIRESTORE_PROJECT_ENV) or None)
    raise StoreMisconfigured(
        f"{STORE_BACKEND_ENV}={name!r} is not a known backend; use 'firestore' or 'memory'"
    )


def default_ingest() -> IngestEndpoint:
    """The ingest endpoint the deployed service serves.

    Reads the shared secret from the environment and raises
    :class:`~deadman.ingest.auth.IngestNotConfigured` when there is none. That
    raise happens at import, which is the whole point: the deploy fails
    visibly instead of accepting unsigned batches.
    """
    return IngestEndpoint(store=default_store(), secret=secret_from_env())


app = make_app(default_probes, self_log=default_self_log(), ingest=default_ingest())


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    with make_server("0.0.0.0", port, app) as httpd:  # noqa: S104 — Cloud Run requires binding all interfaces
        httpd.serve_forever()


if __name__ == "__main__":
    main()
