"""The collector process: sweep, sign, ship — and never drop what it saw.

**Store-and-forward has an ordering, and the ordering is the whole point.**
Every real run drains whatever a prior run could not deliver *before*
attempting the current sweep, oldest evidence first. If the network is still
down, draining stops at the first failure rather than burning through the
rest of the queue for nothing, and the fresh sweep is spooled behind it in
turn. Nothing here decides a batch is undeliverable and throws it away; the
only two outcomes for a row of evidence are "shipped" and "still spooled".

**A resend is a fresh signature, not a replayed one.** :mod:`deadman.ingest.
auth` bounds ``signed_at`` to a five-minute window on arrival, and a spooled
batch can sit for far longer than that while a network is down. Reusing the
original signature would make an honest retry look like a stale replay and
get rejected by the exact check it should sail through. So every send —
first attempt or the tenth retry of a spooled batch — builds a fresh
:class:`~deadman.ingest.wire.Batch` with the current clock reading and signs
that, while the evidence rows themselves keep their original ``read_at``
untouched. What changes on a retry is only when we said we were sending it.

**Dry run touches neither the spool nor the transport.** It sweeps, builds
the batch that *would* be sent, and prints it — nothing is written to disk
and :attr:`Collector.transport` is never called, which is what lets a test
assert zero network calls by running dry-run under a real
:class:`~deadman.collector.transport.UrllibTransport` inside the suite's
hermetic socket block instead of only against a mock.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deadman.collector.config import ConfigError, build_probes, load_config
from deadman.collector.spool import Spool
from deadman.collector.transport import Transport, TransportError, UrllibTransport
from deadman.evidence.model import Evidence
from deadman.ingest.auth import SIGNATURE_HEADER, IngestNotConfigured, secret_from_env, sign
from deadman.ingest.endpoint import EVIDENCE_PATH
from deadman.ingest.wire import Batch, dumps, encode_batch
from deadman.probes.base import Probe, sweep

_STATUS_OK = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Collector:
    """Sweeps its configured probes and ships their evidence, spooling
    whatever it could not deliver rather than dropping it."""

    config: Any
    secret: bytes
    probes: list[Probe]
    transport: Transport = field(default_factory=UrllibTransport)
    clock: Callable[[], datetime] = field(default=_now)

    def __post_init__(self) -> None:
        self.spool = Spool(path=self.config.spool_dir)

    @property
    def evidence_url(self) -> str:
        return f"{self.config.ingest_url}{EVIDENCE_PATH}"

    def run_once(self, dry_run: bool = False) -> dict[str, object]:
        """One collector cycle. Never raises on a probe or a network
        failure — see :func:`deadman.probes.base.sweep` and the module
        docstring's ordering for why."""
        evidence = tuple(sweep(self.probes))

        if dry_run:
            batch = self._build_batch(evidence, self.clock())
            return {"dry_run": True, "swept": len(evidence), "batch": encode_batch(batch)}

        drained = self._drain_spool()
        delivered = self._deliver(evidence)
        return {
            "dry_run": False,
            "swept": len(evidence),
            "delivered": delivered,
            "drained": drained,
        }

    def _build_batch(self, rows: tuple[Evidence, ...], moment: datetime) -> Batch:
        return Batch(collector_id=self.config.collector_id, signed_at=moment, rows=rows)

    def _send(self, rows: tuple[Evidence, ...], moment: datetime) -> bool:
        """Sign and ship one batch, freshly, at ``moment``. ``True`` only on
        a confirmed 200 — a bad status is a real answer from a real service,
        not a network failure, but it still means the batch was not
        accepted, so it is treated the same as unreachable for
        store-and-forward's purposes."""
        batch = self._build_batch(rows, moment)
        body = dumps(batch)
        headers = {"Content-Type": "application/json", SIGNATURE_HEADER: sign(body, self.secret)}
        try:
            status = self.transport.post(self.evidence_url, body, headers)
        except TransportError:
            return False
        return status == _STATUS_OK

    def _deliver(self, rows: tuple[Evidence, ...]) -> bool:
        if not rows:
            return True
        moment = self.clock()
        if self._send(rows, moment):
            return True
        self.spool.enqueue(rows, when=moment)
        return False

    def _drain_spool(self) -> int:
        drained = 0
        for item in self.spool.pending():
            if self._send(item.rows, self.clock()):
                self.spool.drop(item)
                drained += 1
            else:
                break  # the network is still down; the rest can wait too
        return drained


def build_collector(config_path: Path, transport: Transport | None = None) -> Collector:
    """Everything :func:`main` needs, assembled from a config file and the
    environment. Raises :class:`~deadman.collector.config.ConfigError` or
    :class:`~deadman.ingest.auth.IngestNotConfigured` rather than starting
    with something half-wired."""
    config = load_config(config_path)
    secret = secret_from_env()
    probes = build_probes(config.probes)
    return Collector(
        config=config, secret=secret, probes=probes, transport=transport or UrllibTransport()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deadman-collector")
    parser.add_argument(
        "--config", required=True, type=Path, help="path to the collector's config file"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the batch that would ship; touch nothing"
    )
    args = parser.parse_args(argv)

    try:
        collector = build_collector(args.config)
    except (ConfigError, IngestNotConfigured) as exc:
        print(f"deadman-collector: {exc}", file=sys.stderr)
        return 1

    result = collector.run_once(dry_run=args.dry_run)
    if args.dry_run:
        print(json.dumps(result["batch"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
