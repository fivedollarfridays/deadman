#!/usr/bin/env python3
"""Regenerate ``sample-outputs/``.

Every file in that directory is written by this script and none of it is
hand-written. ``tests/test_sample_outputs.py`` enforces that by regenerating
into a temp directory and comparing byte for byte, so a sample tidied by hand
fails the suite rather than quietly advertising output the system does not
produce.

**Deterministic on purpose.** Timestamps are fixed and the model is replayed
from ``tests/recorded/captured-disk-cascade.json``, a real Gemini response.
Samples that changed every run could not be diffed in review, which would hide
a genuine behaviour change inside the churn.

    python scripts/generate_samples.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from recordings import RecordedClient  # noqa: E402

from deadman.correlate.engine import Correlator  # noqa: E402
from deadman.correlate.report import as_dict, render  # noqa: E402
from deadman.diagnose.engine import DiagnosisEngine  # noqa: E402
from deadman.probes.disk import DiskProbe  # noqa: E402
from deadman.probes.morning_brief import MorningBriefProbe  # noqa: E402
from deadman.remediate.actions import default_registry  # noqa: E402
from deadman.remediate.executor import Executor  # noqa: E402
from deadman.remediate.registry import Capabilities  # noqa: E402
from deadman.self_check import Liveness, SelfEvidenceLog, self_check  # noqa: E402
from deadman.service import build_board  # noqa: E402

#: Fixed so every run produces identical bytes.
NOW = datetime(2026, 8, 11, 6, 0, tzinfo=timezone.utc)

CAPTURE = "captured-disk-cascade"

SAMPLES = (
    "board.json",
    "incident.txt",
    "incident.json",
    "remediation-plan.json",
    "self-check.txt",
)


#: Values that legitimately differ between machines and between runs. Redacted
#: rather than invented: the sample shows the real shape of real output with
#: host-specific numbers marked as such, and never a number nobody measured.
VOLATILE = (
    "free_bytes",
    "free_gb",
    "total_gb",
    "pct_free",
    "samples",
    "slope_gb_per_day",
    "runway_days",
)

REDACTED = "<varies by host>"


def _fixed(board: dict, work: Path) -> dict:
    """Redact host-specific values so the board is diffable in review.

    A sample that changes on every run cannot be reviewed, because a genuine
    behaviour change would be invisible inside the churn. What gets redacted
    is only ever a measurement of this particular machine; structure,
    observation, method and provenance are untouched, and no value here is
    fabricated.
    """
    for row in board["surfaces"]:
        row["read_at"] = NOW.isoformat()
        # The generator runs from a temp directory whose path differs per run.
        row["source"] = row["source"].replace(str(work), "<work>")
        if row["surface"].startswith("host:disk"):
            row["summary"] = REDACTED
        for key in VOLATILE:
            if key in row.get("detail", {}):
                row["detail"][key] = REDACTED
    return board


def _board(out: Path, work: Path) -> None:
    """A live sweep of the two credential-free probes, as the service serves it."""
    board = build_board(
        [
            DiskProbe(history_path=work / "disk-history.jsonl"),
            MorningBriefProbe(log_path=work / "absent" / "morning-brief.jsonl"),
        ]
    )
    (out / "board.json").write_text(json.dumps(_fixed(board, work), indent=2) + "\n")


def _incident(out: Path) -> None:
    """The cascade, diagnosed by a replayed real Gemini response."""
    client = RecordedClient(CAPTURE)
    incidents = Correlator(diagnosis=DiagnosisEngine(client=client)).correlate(client.bundle)
    incident = incidents[0]
    (out / "incident.txt").write_text(render(incident) + "\n")
    (out / "incident.json").write_text(json.dumps(as_dict(incident), indent=2, default=str) + "\n")


def _plan(out: Path) -> None:
    """What the executor decides, and why. Selection keys on the diagnosis."""
    client = RecordedClient(CAPTURE)
    bundle = client.bundle
    diagnosis = DiagnosisEngine(client=client).diagnose(bundle)
    executor = Executor(
        registry=default_registry(),
        capabilities=Capabilities(reclaim_space=lambda surface: 0),
    )
    plan = executor.plan(diagnosis, bundle)
    (out / "remediation-plan.json").write_text(
        json.dumps(
            {
                "decision": plan.decision.value,
                "cause": plan.cause.value,
                "reason": plan.reason,
                "action": plan.action,
                "intent": plan.intent,
                "confidence": plan.confidence,
                "diagnosis_status": plan.diagnosis_status,
                "evidence_ids": list(plan.evidence_ids),
            },
            indent=2,
        )
        + "\n"
    )


def _self_check(out: Path, work: Path) -> None:
    """All three liveness states, since the interesting ones are the bad ones."""
    lines = []
    for label, age in (("live", 1.0), ("stale", 100.0), ("no_evidence", None)):
        path = work / f"self-{label}.jsonl"
        if age is not None:
            SelfEvidenceLog(path=path).record(
                sweep_size=2, blind=1, when=NOW - timedelta(hours=age)
            )
        result = self_check(SelfEvidenceLog(path=path), window_hours=30, now=NOW)
        summary = result.summary.replace(str(work), "<tmp>")
        lines.append(f"$ deadman-self-check   # {label}")
        lines.append(f"{result.liveness.value}: {summary}")
        lines.append(f"exit={result.exit_code}")
        lines.append("")
        assert (result.liveness is Liveness.LIVE) == (result.exit_code == 0)
    (out / "self-check.txt").write_text("\n".join(lines))


def generate(out: Path) -> None:
    """Write every sample into ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    work = out / ".work"
    work.mkdir(exist_ok=True)

    _board(out, work)
    _incident(out)
    _plan(out)
    _self_check(out, work)

    for stray in work.iterdir():
        stray.unlink()
    work.rmdir()


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "sample-outputs"
    generate(out)
    for name in SAMPLES:
        print(f"wrote sample-outputs/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
