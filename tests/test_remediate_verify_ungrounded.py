"""An ungrounded diagnosis must not crash the loop.

Found by rehearsing the live demo. Two identical runs against real Gemini
produced different results: one grounded and cited, one substantively correct
but citing nothing, which the grounding layer correctly rejected. On the
second, ``verify_remediation`` raised ``ValueError`` and took the process
down.

The guard it tripped is right in spirit. Verifying against a probe the
diagnosis never cited proves nothing, so refusing is correct. But it cannot
tell apart two different situations:

* the caller passed an unrelated probe, which is a programmer error and
  should be loud, and
* the diagnosis cited nothing at all because the model's answer was thrown
  out, which is ordinary runtime reality on a non-deterministic model and is
  already handled downstream by escalation.

Crashing on the second one means a monitor whose model has an off moment
stops being a monitor. That is the failure mode this project exists to
prevent, arriving through the front door.
"""

from __future__ import annotations

import pytest

from deadman.diagnose.schema import Diagnosis, DiagnosisStatus
from deadman.evidence.model import Evidence, Method, Observation
from deadman.probes.morning_brief import MorningBriefProbe
from deadman.remediate.actions import default_registry
from deadman.remediate.executor import Executor
from deadman.remediate.verify import VerificationStatus, verify_remediation


def _evidence() -> list[Evidence]:
    return [
        Evidence(
            surface="cron:morning-brief",
            observation=Observation.FAULT,
            method=Method.LOCAL_ARTIFACT,
            summary="no brief sent in 218.4h",
            source="/var/log/deadman/morning-brief.jsonl",
            detail={"age_hours": 218.4},
        )
    ]


def _ungrounded() -> Diagnosis:
    """What the engine returns when every citation was rejected."""
    return Diagnosis(
        status=DiagnosisStatus.UNGROUNDED,
        hypothesis="the relay host is refusing sends",
        confidence=0.0,
        claimed_confidence=0.9,
        evidence_ids=(),
        citations=(),
        model="gemini-3.5-flash",
        temperature=0.0,
        prompt_version="diagnose/v1",
        rejected_claims=("cited nothing",),
    )


def test_an_ungrounded_diagnosis_reports_not_attempted_rather_than_raising(tmp_path):
    probe = MorningBriefProbe(log_path=tmp_path / "brief.jsonl")
    executor = Executor(registry=default_registry())

    outcome = verify_remediation(executor, probe, _ungrounded(), _evidence())

    assert outcome.status is VerificationStatus.NOT_ATTEMPTED
    assert outcome.attempts == ()


def test_an_unrelated_probe_still_raises_on_a_grounded_diagnosis(tmp_path):
    # The guard must stay loud for the case it was written for: a caller
    # verifying against a probe the diagnosis never rested on.
    grounded = Diagnosis(
        status=DiagnosisStatus.GROUNDED,
        hypothesis="disk is full",
        confidence=0.8,
        claimed_confidence=0.8,
        evidence_ids=("host:disk/#abc12345",),
        citations=(),
        model="gemini-3.5-flash",
        temperature=0.0,
        prompt_version="diagnose/v1",
    )
    probe = MorningBriefProbe(log_path=tmp_path / "brief.jsonl")

    with pytest.raises(ValueError, match="not among the surfaces"):
        verify_remediation(Executor(registry=default_registry()), probe, grounded, _evidence())
