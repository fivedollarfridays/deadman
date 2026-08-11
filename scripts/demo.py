#!/usr/bin/env python3
"""The break-and-heal demo, runnable start to finish in one unedited take.

Every layer here is the shipped code path: real probes, a real Gemini call
through the ADK, real deterministic selection, the real verification loop.

**What is simulated, stated plainly.** The SMS relay is a stub standing in for
the phone. Nothing else is faked. A carrier outage cannot be arranged on
demand for a demo, so the one thing we cannot break on command is the one
thing injected, using the same `RelayClient` seam the probe already exposes
for tests. The failure it reports (an HTTP 503 from the relay host) is a real
shape that rail produces, and every layer above it is doing real work on it.

    python scripts/demo.py            # replayed model response, no network
    python scripts/demo.py --live     # real Gemini call, needs GCP env

See docs/DEMO.md for the narration and the rehearsed runtime.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from deadman.correlate.engine import Correlator  # noqa: E402
from deadman.diagnose.engine import DiagnosisEngine  # noqa: E402
from deadman.probes.base import blind_spots, sweep  # noqa: E402
from deadman.probes.sms_relay import (  # noqa: E402
    DispatchOutcome,
    DispatchResult,
    SmsRelayProbe,
)
from deadman.remediate.actions import default_registry  # noqa: E402
from deadman.remediate.alert import AlertChannel  # noqa: E402
from deadman.remediate.executor import Executor  # noqa: E402
from deadman.remediate.registry import Capabilities  # noqa: E402
from deadman.remediate.verify import verify_remediation  # noqa: E402
from deadman.self_check import Liveness, SelfEvidenceLog, run_self_check  # noqa: E402

RULE = "─" * 74


def stage(number: int, title: str) -> None:
    print(f"\n{RULE}\n  {number}. {title}\n{RULE}")


def beat(seconds: float = 0.6) -> None:
    """A pause so a viewer can read a line before the next one lands."""
    time.sleep(seconds)


@dataclass
class StubRelay:
    """Stands in for the phone. Broken until the queue is drained."""

    broken: bool = True
    sent: set[str] = field(default_factory=set)
    attempts: int = 0

    def send_canary(self, token: str) -> DispatchResult:
        self.attempts += 1
        if self.broken:
            return DispatchResult(
                outcome=DispatchOutcome.REJECTED,
                why="relay host returned 503 Service Unavailable",
                detail={"http_status": 503, "endpoint": "termux-sms-send"},
            )
        self.sent.add(token)
        return DispatchResult(outcome=DispatchOutcome.ACCEPTED, detail={"http_status": 200})

    def find(self, token: str) -> bool:
        """Sent-folder reader: the only place a canary is confirmed."""
        return token in self.sent


@dataclass
class ScriptedClient:
    """A stand-in model for rehearsal, so the demo runs with no network.

    **This is not a model and does not pretend to be one.** It reads the
    evidence ids and summaries back out of the prompt and returns a
    correctly-shaped response citing them. It exists because the committed
    recordings cite fixed ids, while this demo generates fresh evidence with a
    new canary token every run, so no static recording can ever resolve
    against it.

    The submitted demo runs with ``--live``. This path is for rehearsing the
    sequence and for proving the *pipeline* end to end without spending a call.
    """

    model: str = "scripted-demo-stub"
    temperature: float = 0.0

    def complete(self, prompt: str) -> str:
        import json
        import re

        ids = re.findall(r"^id: (.+)$", prompt, re.MULTILINE)
        summaries = re.findall(r"^summary: (.+)$", prompt, re.MULTILINE)
        citations = [{"evidence_id": i, "quote": s} for i, s in zip(ids, summaries, strict=False)]
        return json.dumps(
            {
                "hypothesis": (
                    "The relay host is refusing sends with a 503, which is an upstream "
                    "outage rather than anything wrong with the credential or the "
                    "message. The evidence does not say how long it will last."
                ),
                "confidence": 0.8,
                "citations": citations,
            }
        )


def _client(live: bool):
    if live:
        from deadman.diagnose.gemini import GeminiClient

        return GeminiClient()
    return ScriptedClient()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deadman-demo", description=__doc__)
    parser.add_argument("--live", action="store_true", help="call Gemini for real")
    parser.add_argument("--no-pause", action="store_true", help="run without dramatic pauses")
    args = parser.parse_args(argv)

    pause = (lambda: None) if args.no_pause else beat
    started = time.time()

    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        relay = StubRelay(broken=False)
        probe = SmsRelayProbe(
            relay=relay,
            sent_folder=relay,
            history_path=work / "canary-history.jsonl",
            cadence_hours=0.0,  # every sweep dispatches; this is a demo, not a duty cycle
        )
        self_log = SelfEvidenceLog(path=work / "self-evidence.jsonl")

        stage(1, "Healthy. The canary goes out and comes back.")
        evidence = sweep([probe])
        self_log.record(sweep_size=len(evidence), blind=len(blind_spots(evidence)))
        for row in evidence:
            print(f"  {row.surface}  {row.observation.value.upper()}  via {row.method.value}")
            print(f"     {row.summary}")
        pause()

        stage(2, "Break it. The relay host starts refusing sends.")
        relay.broken = True
        print("  the phone relay now answers 503 Service Unavailable")
        print("  nothing tells deadman this happened. It has to notice.")
        pause()

        stage(3, "Detected, by manufacturing the evidence rather than waiting.")
        evidence = sweep([probe])
        self_log.record(sweep_size=len(evidence), blind=len(blind_spots(evidence)))
        for row in evidence:
            print(f"  {row.surface}  {row.observation.value.upper()}  via {row.method.value}")
            print(f"     {row.summary}")
        print("\n  Silence on this rail is ambiguous: no traffic and a dead rail look")
        print("  identical. The probe never infers health from quiet, it sends its own")
        print("  message and reads the destination back.")
        pause()

        stage(4, f"Diagnose{' with live Gemini' if args.live else ' (scripted stub, no network)'}.")
        engine = DiagnosisEngine(client=_client(args.live))
        diagnosis = engine.diagnose(evidence)
        print(f"  status     : {diagnosis.status.value}")
        print(f"  confidence : {diagnosis.confidence}")
        print(f"  hypothesis : {diagnosis.hypothesis}")
        print(f"  cites      : {', '.join(diagnosis.evidence_ids) or '(nothing)'}")
        for reason in diagnosis.rejected_claims:
            print(f"  REJECTED   : {reason}")
        pause()

        stage(5, "One fault is not a pattern.")
        incidents = Correlator(diagnosis=engine).correlate(evidence)
        print(f"  correlated incidents: {len(incidents)}")
        print("  A single isolated fault never invents a correlation. Co-occurrence is")
        print("  the whole basis for inferring a shared cause, and there is none here.")
        pause()

        stage(6, "Select. Deterministic, and keyed on the cause rather than the fault.")
        executor = Executor(
            registry=default_registry(),
            capabilities=Capabilities(requeue=lambda surface: _drain(relay, surface)),
        )
        plan = executor.plan(diagnosis, evidence)
        print(f"  cause    : {plan.cause.value}")
        print(f"  decision : {plan.decision.value}")
        print(f"  action   : {plan.action}")
        print(f"  reason   : {plan.reason}")
        print("\n  A 5xx earns an immediate retry. An expired credential would not:")
        print("  re-queueing that fails identically and burns the rate limit.")
        pause()

        stage(7, "Act, then prove it. Success is a fresh observation, not a return value.")
        outcome = verify_remediation(executor, probe, diagnosis, evidence)
        print(f"  status   : {outcome.status.value}")
        print(f"  attempts : {len(outcome.attempts)}")
        for attempt in outcome.attempts:
            plan_taken = attempt.remediation.plan
            seen = attempt.reobservation
            print(f"     acted   : {plan_taken.action} ({plan_taken.decision.value})")
            if seen is not None:
                print(f"     re-read : {seen.surface} -> {seen.observation.value.upper()}")
                print(f"               {seen.summary}")
        print("\n  The executor returning True proves the code ran. It does not prove the")
        print("  rail recovered. The probe was re-run to establish that separately.")
        pause()

        stage(8, "And who watches this? It has to answer that itself.")
        alert_sent: list[str] = []
        channel = AlertChannel(
            transport="email:ops@example.com",
            send=alert_sent.append,
            monitored=("sms:relay", "cron:morning-brief", "host:disk/"),
        )
        live_result = run_self_check(self_log, window_hours=30, channel=channel)
        print(f"  self-check : {live_result.liveness.value} (exit {live_result.exit_code})")

        dead = SelfEvidenceLog(path=work / "never-ran.jsonl")
        dead_result = run_self_check(dead, window_hours=30, channel=channel)
        print(f"  if it died : {dead_result.liveness.value} (exit {dead_result.exit_code})")
        print(f"  alerts out of band: {len(alert_sent)}")
        print("\n  The alarm cannot travel over a rail deadman watches. Configuring it on")
        print("  sms:relay raises at startup, because a self-concealing outage is what")
        print("  this whole system exists to prevent.")

        # The self-liveness half must always hold: it is deterministic.
        ok = (
            live_result.liveness is Liveness.LIVE
            and dead_result.exit_code != 0
            and len(alert_sent) == 1
        )

        healed = outcome.status.value == "verified"
        refused = outcome.status.value == "not_attempted"

    print(f"\n{RULE}")
    if ok and healed:
        print("  DEMO COMPLETE — broke it, found it, fixed it, proved it")
    elif ok and refused:
        # Not a failure, and saying so would be the dishonesty this project is
        # against. On roughly one run in four the model returns a correct-
        # sounding hypothesis citing nothing, grounding throws it out, and
        # nothing is allowed to act on it. That is the system working.
        print("  DEMO COMPLETE — the model did not ground its answer, so nothing acted")
        print("  This is the designed behaviour, not a crash. An uncited hypothesis")
        print("  never reaches an action. Re-run to see the heal path.")
    else:
        print("  DEMO FAILED — a deterministic step did not hold")
    print(f"  {time.time() - started:.1f}s")
    print(RULE)
    return 0 if ok else 1


def _drain(relay: StubRelay, surface: str) -> bool:
    """The requeue capability: the upstream clears and pending work goes out.

    Deliberately a callable the deployment supplies. Nothing in the remediation
    package holds a live handle to anyone's infrastructure.
    """
    relay.broken = False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
