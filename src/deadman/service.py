"""The Cloud Run service: publishes the current board, and takes evidence in.

A plain WSGI callable, no framework. The package declares zero runtime
dependencies (see ``pyproject.toml``); pulling in a web framework for three
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

``POST /self-check`` is Cloud Scheduler's endpoint, not a human's: it runs the
same local sweep on a cadence the deployment controls, and writes its own
liveness through the DM2.1 store rather than this instance's filesystem, so
the claim survives a cold start. See :mod:`deadman.scheduled`.

**This module refuses to import without an ingest secret and a scheduler
secret.** ``app`` is built at module scope and building it reads the
environment, so an unconfigured deploy dies at startup rather than serving an
endpoint that would accept evidence, or a trigger, from anyone who can reach
the URL.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from wsgiref.simple_server import make_server

from deadman import board as board_memory
from deadman import redact
from deadman import scheduled as scheduled_pkg
from deadman.evidence.model import Evidence, Observation
from deadman.ingest.auth import secret_from_env
from deadman.ingest.endpoint import EVIDENCE_PATH, IngestEndpoint
from deadman.probes.base import Probe, blind_spots, sweep
from deadman.probes.disk import DiskProbe
from deadman.probes.morning_brief import MorningBriefProbe
from deadman.self_check import SelfEvidenceLog, StoreSelfEvidenceLog
from deadman.store import EvidenceStore, FirestoreEvidenceStore, InMemoryEvidenceStore
from deadman.verify.collector_liveness import LivenessReport, assess
from deadman.verify.expectations import CollectorExpectation, load_expectations

ProbesFn = Callable[[], list[Probe]]
LivenessFn = Callable[[], LivenessReport | None]

#: Which :mod:`deadman.store` backend the service writes ingested evidence to.
STORE_BACKEND_ENV = "DEADMAN_STORE_BACKEND"

#: GCP project for the Firestore backend. Unset means the SDK's own default.
FIRESTORE_PROJECT_ENV = "DEADMAN_FIRESTORE_PROJECT"

#: Path to the collector liveness declaration — which collectors are expected
#: to report, how often, and about what. See :mod:`deadman.verify.expectations`
#: and ``infra/collector/collectors.example.json``.
COLLECTORS_ENV = "DEADMAN_COLLECTORS"

#: Send log the morning-brief probe reads. Set empty to drop the probe from
#: this process entirely — the explicit opt-out for deployments (Cloud Run)
#: where the log cannot exist and the surface arrives via ingest instead.
BRIEF_LOG_ENV = "DEADMAN_BRIEF_LOG"


_METHOD_NOT_ALLOWED = "405 Method Not Allowed"


class StoreMisconfigured(RuntimeError):
    """The configured store backend is not one that exists."""


def default_probes() -> list[Probe]:
    """Probes safe to run anywhere, Cloud Run included: no credentials, no
    outbound network. Everything else (Metricool, destinations, SMS relay)
    needs secrets this endpoint does not hold."""
    brief_log = os.environ.get(BRIEF_LOG_ENV, "/var/log/deadman/morning-brief.jsonl")
    disk_history = Path(os.environ.get("DEADMAN_DISK_HISTORY", "/tmp/deadman/disk-history.jsonl"))
    probes: list[Probe] = [DiskProbe(history_path=disk_history)]
    if brief_log:
        # Empty means deliberately disabled, not defaulted: a deploy where the
        # log cannot exist gets its brief evidence from a collector, and a
        # probe that can only ever answer "unobservable" adds a permanent
        # blind spot to the board without watching anything.
        probes.append(MorningBriefProbe(log_path=Path(brief_log)))
    return probes


def _evidence_row(evidence: Evidence, history: Sequence[Evidence] = ()) -> dict[str, object]:
    """One board row, redacted for an unauthenticated reader.

    ``GET /`` is deployed ``--allow-unauthenticated`` and its URL is published,
    so everything here is world-readable. Before DM2 the rows came only from
    probes running in this process; ingest means they now carry a collector's
    absolute paths, its id, and our arrival times, and publishing those verbatim
    hands a stranger a map of Kevin's machines.

    ``reported_by`` (:func:`deadman.board.reported_by`) is a deliberate
    exception to that gate, not a loosening of it: a collector's id is already
    public in its own liveness surface name (``collector:kevin-mac``), so
    naming it again here reveals nothing new. It is absent, not null, when the
    row is one of the service's own probes.

    ``held_since``/``held_seconds`` come from ``history`` via
    :func:`deadman.board.held_since` — how long the row's current observation
    has held, walked back through stored history rather than restated from
    this one reading.
    """
    since = board_memory.held_since(evidence, history)
    row: dict[str, object] = {
        "surface": evidence.surface,
        "observation": evidence.observation.value,
        "method": evidence.method.value,
        "summary": evidence.summary,
        "source": redact.public_source(evidence.source),
        "read_at": evidence.read_at.isoformat(),
        "detail": redact.public_detail(evidence.detail),
        "held_since": since.isoformat(),
        "held_seconds": round((evidence.read_at - since).total_seconds(), 1),
    }
    by = board_memory.reported_by(evidence)
    if by is not None:
        row["reported_by"] = by
    return row


def build_board(
    probes: list[Probe],
    self_log: SelfEvidenceLog | None = None,
    liveness: LivenessReport | None = None,
    store: EvidenceStore | None = None,
) -> dict[str, object]:
    """The current board: every probe's evidence plus the counts a human
    reads first. Blind spots get their own field per ``base.blind_spots`` —
    a summary that folds them into "healthy" is the lie this project is
    about.

    When ``self_log`` is given, a row is appended *after* the sweep completes.
    That row is the only evidence deadman has that it is alive (see
    ``deadman.self_check``), and it is written here rather than at startup on
    purpose: what needs proving is that a sweep finished, not that a process
    began. It counts the sweep alone: liveness is read back out of the store,
    not swept, and letting it inflate the number would let a service whose
    probes all failed still look like it did some work.

    ``liveness`` (:mod:`deadman.verify.collector_liveness`) contributes the
    rows a local sweep structurally cannot produce — a collector that has gone
    quiet, and a surface whose newest reading is older than its declared
    cadence. Without it the board answers "is anything broken here" while
    silently declining to answer "is anyone still reporting", and those two
    look identical from the outside.

    ``store``, when given, is where each row's held-duration is read from
    (see :mod:`deadman.board`) — the same store ingest writes to and liveness
    reads from, so a row's history is never staler than what the rest of the
    board already knows. Omitting it (the local-sweep-only case) is not an
    error: every row still renders a duration, just zero.
    """
    evidence = sweep(probes)
    if self_log is not None:
        self_log.record(sweep_size=len(evidence), blind=len(blind_spots(evidence)))

    rows = [*evidence, *(liveness.rows if liveness is not None else ())]
    blind = blind_spots(rows)
    return {
        "surfaces": [_evidence_row(e, board_memory.history_for(store, e.surface)) for e in rows],
        "blind_spots": [e.surface for e in blind],
        "healthy_count": sum(1 for e in rows if e.observation is Observation.HEALTHY),
        "fault_count": sum(1 for e in rows if e.observation is Observation.FAULT),
        "blind_count": len(blind),
        **_liveness_summary(liveness),
    }


def _liveness_summary(liveness: LivenessReport | None) -> dict[str, object]:
    """The counts that keep "no faults" and "nothing reported" apart.

    ``fresh``, ``stale`` and ``unreported`` partition the declared surfaces,
    so a reader can check they sum to what was declared rather than trusting
    one aggregate. ``collectors_declared`` is on the board for the case those
    three cannot express: zero declared collectors means nobody's silence is
    being watched, and a board of zeroes would otherwise read like an estate
    with nothing wrong.
    """
    if liveness is None:
        return {
            "collectors_declared": 0,
            "fresh_count": 0,
            "stale_count": 0,
            "unreported_count": 0,
            "undeclared_surfaces": [],
        }
    return {
        "collectors_declared": len(liveness.collectors),
        "fresh_count": liveness.fresh,
        "stale_count": liveness.stale,
        "unreported_count": liveness.unreported,
        "undeclared_surfaces": list(liveness.undeclared),
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
    liveness_fn: LivenessFn | None = None,
    scheduled: scheduled_pkg.ScheduledSelfCheckEndpoint | None = None,
    store: EvidenceStore | None = None,
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

    ``liveness_fn`` is read per request for the same reason as ``probes_fn``:
    silence accumulates between requests, so a report computed once at startup
    would answer with how things were when the instance booted.

    ``scheduled`` is the endpoint Cloud Scheduler triggers (see
    :mod:`deadman.scheduled`) — its own path, its own auth, and its own
    self-evidence writer, deliberately separate from ``self_log`` above: that
    one is written on a served board, this one on a cadence, and each must
    keep proving liveness if the other stops.

    ``store`` feeds ``build_board``'s held-duration read (see
    :func:`build_board`), fetched fresh per request for the same reason as
    ``probes_fn``: history accumulates between requests.
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

        if path == scheduled_pkg.SCHEDULED_PATH:
            if method != "POST" or scheduled is None:
                return _respond(
                    start_response, _METHOD_NOT_ALLOWED, {"error": "method not allowed"}
                )
            status, payload = scheduled.handle(environ)
            return _respond(start_response, status, payload)

        if method != "GET":
            return _respond(start_response, _METHOD_NOT_ALLOWED, {"error": "method not allowed"})

        board = build_board(
            probes_fn(),
            self_log=self_log,
            liveness=liveness_fn() if liveness_fn is not None else None,
            store=store,
        )
        return _respond(start_response, "200 OK", board)

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


def default_ingest(store: EvidenceStore | None = None) -> IngestEndpoint:
    """The ingest endpoint the deployed service serves.

    Reads the shared secret from the environment and raises
    :class:`~deadman.ingest.auth.IngestNotConfigured` when there is none. That
    raise happens at import, which is the whole point: the deploy fails
    visibly instead of accepting unsigned batches.
    """
    return IngestEndpoint(store=store or default_store(), secret=secret_from_env())


def default_scheduled(
    store: EvidenceStore | None = None,
    expectations: tuple[CollectorExpectation, ...] | None = None,
) -> scheduled_pkg.ScheduledSelfCheckEndpoint:
    """The scheduled self-check endpoint the deployed service serves.

    Reads the shared secret from the environment and raises
    :class:`~deadman.scheduled.auth.SchedulerNotConfigured` when there is
    none — the same startup refusal :func:`default_ingest` makes, for the
    same reason: a public endpoint that triggers work is a free
    denial-of-service, so an unconfigured deploy must not boot with one.

    Writes through the same store ``default_ingest`` and the liveness reader
    share, via :class:`~deadman.self_check.StoreSelfEvidenceLog`, so the
    self-check's own evidence survives a cold start the way DM1.11's
    filesystem-backed log could not.
    """
    backing = store or default_store()
    expectations = expectations if expectations is not None else default_expectations()
    return scheduled_pkg.ScheduledSelfCheckEndpoint(
        probes_fn=default_probes,
        self_log=StoreSelfEvidenceLog(store=backing),
        secret=scheduled_pkg.secret_from_env(),
        alarm=scheduled_pkg.alerting.default_alarm(backing),
        liveness_fn=(lambda: assess(backing, expectations)) if expectations else None,
    )


def default_expectations() -> tuple[CollectorExpectation, ...]:
    """Which collectors this deployment expects to hear from, and how often.

    A named file that cannot be read or parsed is a startup failure, not a
    fallback: a liveness config with a typo in it is a monitor that watches
    the wrong collectors, and discovering that later means discovering it
    during the outage it failed to report.

    **An unset variable announces itself on stderr**, which Cloud Run
    captures, because the consequence is invisible on the board it produces:
    with nothing declared, a collector can stop reporting forever and the
    board will keep serving whatever the service can see locally, which on
    Cloud Run is almost nothing. That is the ambiguous empty inbox this module
    exists to eliminate, arrived at through configuration instead of failure.
    """
    declared = os.environ.get(COLLECTORS_ENV, "").strip()
    if not declared:
        print(
            f"deadman: no collector liveness config ({COLLECTORS_ENV} is unset), so no "
            f"collector's silence will be noticed and the board cannot distinguish a "
            f"healthy estate from a dead collector. Point it at a declaration file; see "
            f"infra/collector/collectors.example.json.",
            file=sys.stderr,
        )
        return ()
    return load_expectations(Path(declared))


def build_app() -> Callable[[dict, Callable], Iterable[bytes]]:
    """The deployed app, assembled from the environment.

    One store, constructed once and shared: the endpoint that writes collected
    evidence and the liveness that reads it back must be looking at the same
    rows, or the board would report silence from a collector whose delivery
    the service had just accepted.
    """
    store = default_store()
    expectations = default_expectations()
    return make_app(
        default_probes,
        self_log=default_self_log(),
        ingest=default_ingest(store),
        liveness_fn=(lambda: assess(store, expectations)) if expectations else None,
        scheduled=default_scheduled(store, expectations),
        store=store,
    )


app = build_app()


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    with make_server("0.0.0.0", port, app) as httpd:  # noqa: S104 — Cloud Run requires binding all interfaces
        httpd.serve_forever()


if __name__ == "__main__":
    main()
