"""Break-and-heal against a real surface, with nothing standing in.

The rest of the demo breaks a phone relay through a stub, because a carrier
outage cannot be arranged on demand. This segment has no such excuse and takes
none: ``MorningBriefProbe`` is constructed over a path and holds no client, no
relay and no seam, so what it reads is a real file on a real filesystem, and
what it reports is computed from the real clock.

**The break is the outage's own last row.** The timestamp written is
``tests/fixtures/real-morning-brief-fault.json``'s ``last_send_at`` — the last
morning brief Kevin's estate actually delivered, on 2026-08-04, after which the
job hung every morning and said nothing. Nothing here invents a timestamp
chosen to trip the window.

**The heal is a real write, and it is not what proves the fix.** A repaired
brief job appends a row after a verified send; the segment appends one the same
way. What says the surface recovered is the *next observation* of the same
probe, which is the standard the verification loop holds an automated
remediation to (:mod:`deadman.remediate.verify`).

**The correct automated outcome here is a human.** No shipped action fixes a
hung cron job on somebody's laptop, so the cause classifies ``UNKNOWN`` and the
executor escalates rather than guessing. The alarm goes out over email — a rail
deadman does not watch — because an alert over the morning brief is exactly the
self-concealing outage this project is named after.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from deadman.diagnose.engine import DiagnosisEngine
from deadman.diagnose.schema import Diagnosis
from deadman.evidence.model import Evidence, Observation
from deadman.probes.base import run_probe
from deadman.probes.morning_brief import MorningBriefProbe
from deadman.remediate.actions import default_registry
from deadman.remediate.alert import AlertChannel
from deadman.remediate.cause import Cause, classify
from deadman.remediate.executor import Executor
from deadman.remediate.registry import Capabilities
from deadman.remediate.verify import VerificationOutcome, verify_remediation

#: The committed capture of the real outage. Read rather than transcribed: a
#: timestamp copied into source is a timestamp that can drift from the evidence
#: it claims to come from.
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
CAPTURE = FIXTURES / "real-morning-brief-fault.json"

#: The surfaces deadman actually watches on this estate (``docs/surfaces.md``).
#: Passed to the alert channel so "out of band" is checked against the real
#: list rather than a convenient one.
MONITORED = ("cron:morning-brief", "host:mac/disk", "host:rig/disk", "collector:kevin-mac")

#: Not a rail deadman watches, which is the whole requirement.
ALERT_TRANSPORT = "email:ops@example.com"


@dataclass(frozen=True)
class RealSurfaceRun:
    """Every stage of the segment, kept so the demo prints what happened rather
    than a narration of what usually happens."""

    healthy: Evidence
    broken: Evidence
    diagnosis: Diagnosis
    cause: Cause
    outcome: VerificationOutcome
    healed: Evidence
    channel: AlertChannel
    alerts: tuple[str, ...]


def outage_last_send_at() -> str:
    """When the real brief last delivered, out of the committed capture."""
    return json.loads(CAPTURE.read_text())["evidence"]["detail"]["last_send_at"]


def probe_for(log_path: Path) -> MorningBriefProbe:
    """The shipped probe, over a real path. No arguments a demo could use to
    reach past it and hand it an answer."""
    return MorningBriefProbe(log_path=log_path)


def send_row(log_path: Path, when: datetime) -> None:
    """Append a send-log row in the shape the ops brief job writes one.

    The probe reads the timestamp *inside* the row, never the file's mtime, so
    a row written now that claims last week is stale — which is what makes the
    break below honest rather than staged.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": when.isoformat(), "event": "brief_sent", "verified": True}
    with log_path.open("a") as handle:
        handle.write(json.dumps(row) + "\n")


def start_healthy(log_path: Path) -> Evidence:
    """A brief delivered just now: the state the estate is supposed to be in."""
    send_row(log_path, datetime.now(timezone.utc))
    return run_probe(probe_for(log_path))


def break_it(log_path: Path) -> Evidence:
    """The job stops delivering, and the log stops growing.

    Rewinding to the outage's own last row is the same thing time would do,
    without waiting seven days for it: the newest row is the 2026-08-04 send,
    and every morning since then added nothing.
    """
    log_path.write_text("")
    send_row(log_path, datetime.fromisoformat(outage_last_send_at()))
    return run_probe(probe_for(log_path))


def heal_it(log_path: Path) -> Evidence:
    """The fix lands, a brief goes out, and a row is appended after the send.

    The returned observation — not this function's return — is what says the
    surface recovered.
    """
    send_row(log_path, datetime.now(timezone.utc))
    return run_probe(probe_for(log_path))


def _escalate(plan_reason: str, evidence: Evidence, channel: AlertChannel) -> None:
    channel.alert(
        f"deadman: {evidence.surface} FAULT — {evidence.summary}. "
        f"No automated action: {plan_reason}"
    )


def run_segment(log_path: Path, client: object) -> RealSurfaceRun:
    """Healthy, broken, diagnosed, escalated, healed, re-observed.

    The channel is built here rather than passed in so the out-of-band check in
    :class:`~deadman.remediate.alert.AlertChannel` runs against ``MONITORED``
    every time this segment does — a caller supplying its own channel could
    supply one on the rail that just died.
    """
    sent: list[str] = []
    channel = AlertChannel(transport=ALERT_TRANSPORT, send=sent.append, monitored=MONITORED)

    healthy = start_healthy(log_path)
    broken = break_it(log_path)

    engine = DiagnosisEngine(client=client)
    diagnosis = engine.diagnose([broken])
    cause = classify([broken])

    executor = Executor(registry=default_registry(), capabilities=Capabilities())
    outcome = verify_remediation(executor, probe_for(log_path), diagnosis, [broken])
    # The alarm answers the FAULT, never the model. It used to fire once per
    # remediation attempt, and an ungrounded diagnosis (about one live run in
    # four) makes no attempt at all — so a real fault raised no alarm.
    # ``deadman.scheduled.alerting.evaluate`` alarms on every FAULT without
    # consulting a diagnosis; this segment now holds itself to the same rule.
    if broken.observation is Observation.FAULT:
        _escalate(executor.plan(diagnosis, [broken]).reason, broken, channel)

    healed = heal_it(log_path)

    return RealSurfaceRun(
        healthy=healthy,
        broken=broken,
        diagnosis=diagnosis,
        cause=cause,
        outcome=outcome,
        healed=healed,
        channel=channel,
        alerts=tuple(sent),
    )
