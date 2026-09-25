"""A real fault raises its alarm whatever the model said about it.

Found live on 2026-09-25: ``scripts/demo.py --live`` crashed at stage one with
``IndexError`` on ``run.alerts[0]``. The live model had returned an uncited
answer (roughly one run in four, per docs/DEMO.md), grounding rejected it, and
``verify_remediation`` correctly reported ``NOT_ATTEMPTED`` with no attempts.
``run_segment`` only alarmed *inside* the loop over attempts, so a real FAULT
produced no alarm at all.

That is the failure class this project exists to catch, reproduced in its own
demo: the alarm was coupled to the model's grounding. The shipped alarm path
(:func:`deadman.scheduled.alerting.evaluate`) alarms on every FAULT and never
consults a diagnosis; these tests hold the demo segment to the same rule.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import demo  # noqa: E402
from demo_real_surface import run_segment  # noqa: E402
from demo_stubs import ScriptedClient  # noqa: E402

from deadman.diagnose.schema import DiagnosisStatus  # noqa: E402
from deadman.evidence.model import Observation  # noqa: E402
from deadman.remediate.verify import VerificationStatus  # noqa: E402


@dataclass
class UncitedClient:
    """What live Gemini does about one run in four: a plausible hypothesis
    that cites nothing, which grounding must throw out."""

    model: str = "uncited-stub"
    temperature: float = 0.0

    def complete(self, prompt: str) -> str:
        return json.dumps(
            {
                "hypothesis": "The morning brief job has hung and stopped sending.",
                "confidence": 0.9,
                "citations": [],
            }
        )


def _log(tmp_path: Path) -> Path:
    return tmp_path / "brief-send-log.jsonl"


def test_an_ungrounded_diagnosis_still_raises_exactly_one_alarm(tmp_path):
    run = run_segment(_log(tmp_path), UncitedClient())

    assert run.diagnosis.status is not DiagnosisStatus.GROUNDED
    assert run.outcome.status is VerificationStatus.NOT_ATTEMPTED
    assert run.outcome.attempts == ()
    assert run.broken.observation is Observation.FAULT
    assert len(run.alerts) == 1
    assert "cron:morning-brief" in run.alerts[0]


def test_the_ungrounded_alarm_says_why_nothing_was_automated(tmp_path):
    run = run_segment(_log(tmp_path), UncitedClient())

    assert run.diagnosis.status.value in run.alerts[0]
    assert "No automated action" in run.alerts[0]


def test_the_grounded_path_still_raises_exactly_one_alarm(tmp_path):
    run = run_segment(_log(tmp_path), ScriptedClient())

    assert run.diagnosis.status is DiagnosisStatus.GROUNDED
    assert len(run.alerts) == 1
    assert "no rule recognised this failure" in run.alerts[0]


def test_stage_one_fails_loudly_rather_than_crashing_on_no_alarm(tmp_path, monkeypatch, capsys):
    """Whatever regresses upstream, the demo must say the alarm is missing
    and fail the stage, never die on an IndexError mid-take."""
    real = run_segment(_log(tmp_path), ScriptedClient())
    monkeypatch.setattr(demo, "run_segment", lambda *_: replace(real, alerts=()))

    ok = demo._stage_real_surface(ScriptedClient(), tmp_path)

    assert ok is False
    assert "NO ALARM" in capsys.readouterr().out
