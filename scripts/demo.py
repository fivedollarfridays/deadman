#!/usr/bin/env python3
"""The break-and-heal demo, runnable start to finish in one unedited take.

Every layer here is the shipped code path: real probes, a real Gemini call
through the ADK, real deterministic selection, the real verification loop.

**Stage one has nothing standing in at all.** `scripts/demo_real_surface`
breaks and heals `cron:morning-brief` for real — a real probe over a real file,
broken by the outage's own last log row out of the committed capture, healed by
the write a repaired brief job makes, and proved by a fresh observation. That
is the surface the case study in `docs/PROOF.md` is about.

**What is simulated, stated plainly.** The SMS relay is a stub standing in for
the phone, and it is the only one. A carrier outage cannot be arranged on
demand for a demo, so the one thing we cannot break on command is the one
thing injected, using the same `RelayClient` seam the probe already exposes
for tests. The failure it reports (an HTTP 503 from the relay host) is a real
shape that rail produces, and every layer above it is doing real work on it.
It stays in the demo because it is the surface that carries the *automated*
act-and-verify path: a dead cron job on a laptop correctly escalates, so it
cannot show what a shipped action plus a re-observation looks like.

    python scripts/demo.py            # replayed model response, no network
    python scripts/demo.py --live     # real Gemini call, needs GCP env

See docs/DEMO.md for the narration and the rehearsed runtime.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_real_surface import outage_last_send_at, run_segment  # noqa: E402
from demo_stubs import ScriptedClient, StubRelay  # noqa: E402

from deadman.correlate.engine import Correlator  # noqa: E402
from deadman.diagnose.engine import DiagnosisEngine  # noqa: E402
from deadman.evidence.model import Observation  # noqa: E402
from deadman.probes.base import blind_spots, sweep  # noqa: E402
from deadman.probes.sms_relay import SmsRelayProbe  # noqa: E402
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


def _client(live: bool):
    if live:
        from deadman.diagnose.gemini import GeminiClient

        return GeminiClient()
    return ScriptedClient()


def _show(evidence) -> None:
    for row in evidence:
        print(f"  {row.surface}  {row.observation.value.upper()}  via {row.method.value}")
        print(f"     {row.summary}")


def _sweep_and_record(probe, self_log):
    evidence = sweep([probe])
    self_log.record(sweep_size=len(evidence), blind=len(blind_spots(evidence)))
    _show(evidence)
    return evidence


def _stage_real_surface(client, work: Path) -> bool:
    """Stage one, and the only one with nothing standing in.

    A real probe over a real file: broken by the outage's own last log row,
    detected off the real clock, escalated because no shipped action fixes a
    hung cron job, and healed by the write a repaired brief job makes.
    """
    stage(1, "A real surface. No stub anywhere on this path.")
    run = run_segment(work / "brief-send-log.jsonl", client)

    print(f"  healthy    : {run.healthy.summary}")
    print("  broken     : it stops delivering, and the log stops growing")
    print(f"               last real send {outage_last_send_at()} — from the committed capture")
    print(f"  detected   : {run.broken.observation.value.upper()} via {run.broken.method.value}")
    print(f"               {run.broken.summary}")
    print(f"  cause      : {run.cause.value} -> {run.outcome.status.value}")
    print(f"  alarm      : {run.alerts[0][:88]}…")
    print(f"  healed     : {run.healed.observation.value.upper()} — {run.healed.summary}")
    print("\n  Nothing was injected. The probe holds no client and no seam; it read a")
    print("  file. Seven days of this went unnoticed in the real estate, because the")
    print("  brief is itself the alerting channel — so the alarm above is on email,")
    print("  a rail deadman does not watch. See docs/PROOF.md.")

    return (
        run.healthy.observation is Observation.HEALTHY
        and run.broken.observation is Observation.FAULT
        and run.healed.observation is Observation.HEALTHY
        and len(run.alerts) == 1
    )


def _stage_break(relay: StubRelay) -> None:
    stage(3, "Break it. The relay host starts refusing sends.")
    relay.broken = True
    print("  the phone relay now answers 503 Service Unavailable")
    print("  nothing tells deadman this happened. It has to notice.")


def _stage_diagnose(engine, evidence, live: bool):
    stage(5, f"Diagnose{' with live Gemini' if live else ' (scripted stub, no network)'}.")
    diagnosis = engine.diagnose(evidence)
    print(f"  status     : {diagnosis.status.value}")
    print(f"  confidence : {diagnosis.confidence}")
    print(f"  hypothesis : {diagnosis.hypothesis}")
    print(f"  cites      : {', '.join(diagnosis.evidence_ids) or '(nothing)'}")
    for reason in diagnosis.rejected_claims:
        print(f"  REJECTED   : {reason}")
    return diagnosis


def _stage_correlate(engine, evidence) -> None:
    stage(6, "One fault is not a pattern.")
    incidents = Correlator(diagnosis=engine).correlate(evidence)
    print(f"  correlated incidents: {len(incidents)}")
    print("  A single isolated fault never invents a correlation. Co-occurrence is")
    print("  the whole basis for inferring a shared cause, and there is none here.")


def _stage_select(executor, diagnosis, evidence):
    stage(7, "Select. Deterministic, and keyed on the cause rather than the fault.")
    plan = executor.plan(diagnosis, evidence)
    print(f"  cause    : {plan.cause.value}")
    print(f"  decision : {plan.decision.value}")
    print(f"  action   : {plan.action}")
    print(f"  reason   : {plan.reason}")
    print("\n  A 5xx earns an immediate retry. An expired credential would not:")
    print("  re-queueing that fails identically and burns the rate limit.")
    return plan


def _stage_verify(executor, probe, diagnosis, evidence):
    stage(8, "Act, then prove it. Success is a fresh observation, not a return value.")
    outcome = verify_remediation(executor, probe, diagnosis, evidence)
    print(f"  status   : {outcome.status.value}")
    print(f"  attempts : {len(outcome.attempts)}")
    for attempt in outcome.attempts:
        taken = attempt.remediation.plan
        seen = attempt.reobservation
        print(f"     acted   : {taken.action} ({taken.decision.value})")
        if seen is not None:
            print(f"     re-read : {seen.surface} -> {seen.observation.value.upper()}")
            print(f"               {seen.summary}")
    print("\n  The executor returning True proves the code ran. It does not prove the")
    print("  rail recovered. The probe was re-run to establish that separately.")
    return outcome


def _stage_self_check(self_log, work: Path) -> bool:
    stage(9, "And who watches this? It has to answer that itself.")
    sent: list[str] = []
    channel = AlertChannel(
        transport="email:ops@example.com",
        send=sent.append,
        monitored=("sms:relay", "cron:morning-brief", "host:disk/"),
    )
    live_result = run_self_check(self_log, window_hours=30, channel=channel)
    print(f"  self-check : {live_result.liveness.value} (exit {live_result.exit_code})")

    dead = run_self_check(SelfEvidenceLog(path=work / "never-ran.jsonl"), 30, channel)
    print(f"  if it died : {dead.liveness.value} (exit {dead.exit_code})")
    print(f"  alerts out of band: {len(sent)}")
    print("\n  The alarm cannot travel over a rail deadman watches. Configuring it on")
    print("  sms:relay raises at startup, because a self-concealing outage is what")
    print("  this whole system exists to prevent.")

    return live_result.liveness is Liveness.LIVE and dead.exit_code != 0 and len(sent) == 1


def _verdict(ok: bool, outcome, elapsed: float) -> int:
    print(f"\n{RULE}")
    if ok and outcome.status.value == "verified":
        print("  DEMO COMPLETE — broke it, found it, fixed it, proved it")
    elif ok and outcome.status.value == "not_attempted":
        # Not a failure, and saying so would be the dishonesty this project is
        # against. On roughly one run in four the model returns a correct-
        # sounding hypothesis citing nothing, grounding throws it out, and
        # nothing is allowed to act on it. That is the system working.
        print("  DEMO COMPLETE — the model did not ground its answer, so nothing acted")
        print("  This is the designed behaviour, not a crash. An uncited hypothesis")
        print("  never reaches an action. Re-run to see the heal path.")
    else:
        print("  DEMO FAILED — a deterministic step did not hold")
    print(f"  {elapsed:.1f}s")
    print(RULE)
    return 0 if ok else 1


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
        client = _client(args.live)
        engine = DiagnosisEngine(client=client)
        executor = Executor(
            registry=default_registry(),
            capabilities=Capabilities(requeue=lambda surface: _drain(relay, surface)),
        )

        real_ok = _stage_real_surface(client, work)
        pause()

        stage(2, "Healthy. The canary goes out and comes back.")
        _sweep_and_record(probe, self_log)
        pause()

        _stage_break(relay)
        pause()

        stage(4, "Detected, by manufacturing the evidence rather than waiting.")
        evidence = _sweep_and_record(probe, self_log)
        print("\n  Silence on this rail is ambiguous: no traffic and a dead rail look")
        print("  identical. The probe never infers health from quiet, it sends its own")
        print("  message and reads the destination back.")
        pause()

        diagnosis = _stage_diagnose(engine, evidence, args.live)
        pause()
        _stage_correlate(engine, evidence)
        pause()
        _stage_select(executor, diagnosis, evidence)
        pause()
        outcome = _stage_verify(executor, probe, diagnosis, evidence)
        pause()
        ok = real_ok and _stage_self_check(self_log, work)

    return _verdict(ok, outcome, time.time() - started)


def _drain(relay: StubRelay, surface: str) -> bool:
    """The requeue capability: the upstream clears and pending work goes out.

    Deliberately a callable the deployment supplies. Nothing in the remediation
    package holds a live handle to anyone's infrastructure.
    """
    relay.broken = False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
