"""Selection: which action a diagnosis earns, and when none of them do.

Every diagnosis here comes out of the real :class:`DiagnosisEngine` replaying a
recorded response, so what is under test is the actual seam between the two
layers rather than a hand-built object that happens to have the right fields.

The recordings share one bundle on purpose. ``bundle-metricool-publish-failure``
holds a single fault class — a scheduled post that never reached the
destination — alongside several candidate causes. Holding the fault constant and
varying only the diagnosis is the whole argument of this task.
"""

from __future__ import annotations

import pytest
from recordings import RaisingClient, RecordedClient, load_bundle

from deadman.diagnose.engine import DiagnosisEngine
from deadman.diagnose.schema import DiagnosisStatus
from deadman.remediate.actions import (
    RECLAIM_SPACE,
    REFRESH_CREDENTIAL,
    RETRY_NOW,
    default_registry,
)
from deadman.remediate.cause import Cause
from deadman.remediate.executor import Decision, Executor
from deadman.remediate.registry import Capabilities

FULLY_CAPABLE = Capabilities(
    requeue=lambda surface: True,
    refresh_credential=lambda channel: True,
    reclaim_space=lambda path: 0,
)


def diagnose(name: str):
    client = RecordedClient(name)
    return DiagnosisEngine(client=client).diagnose(client.bundle), client.bundle


def plan_for(name: str, capabilities: Capabilities = FULLY_CAPABLE):
    diagnosis, evidence = diagnose(name)
    assert diagnosis.status is DiagnosisStatus.GROUNDED, "fixture must be actionable"
    executor = Executor(registry=default_registry(), capabilities=capabilities)
    return executor.plan(diagnosis, evidence)


# --- selection is a function of the diagnosis ----------------------------


def test_one_fault_class_two_diagnoses_two_different_actions():
    """The acceptance criterion, stated as directly as it can be. Same bundle,
    same fault, same surface — the only thing that differs is what the model
    concluded was causal, and that alone changes the action."""
    transient = plan_for("grounded-transient-5xx")
    credential = plan_for("grounded-expired-credential")

    assert transient.action == RETRY_NOW
    assert credential.action == REFRESH_CREDENTIAL
    assert transient.action != credential.action


def test_a_transient_5xx_diagnosis_selects_an_immediate_retry():
    plan = plan_for("grounded-transient-5xx")

    assert plan.decision is Decision.ACT
    assert plan.cause is Cause.TRANSIENT_UPSTREAM
    assert plan.action == RETRY_NOW


def test_an_expired_credential_diagnosis_never_selects_a_retry():
    plan = plan_for("grounded-expired-credential")

    assert plan.cause is Cause.EXPIRED_CREDENTIAL
    assert plan.action != RETRY_NOW
    assert plan.action == REFRESH_CREDENTIAL


def test_the_hypothesis_prose_cannot_talk_the_executor_into_a_retry():
    """``grounded-expired-credential`` is grounded — every cited fact checks
    out — and its prose says in plain English to re-queue the post right away.
    Selection reads the cited evidence, not the sentence, so it does not."""
    diagnosis, _ = diagnose("grounded-expired-credential")

    assert "retry" in diagnosis.hypothesis.lower()
    assert "re-queue" in diagnosis.hypothesis.lower()
    assert plan_for("grounded-expired-credential").action != RETRY_NOW


def test_a_diagnosis_citing_both_causes_still_refuses_the_retry():
    """A 503 is cited and a retry is genuinely indicated by it. The lapsed
    credential cited alongside it makes that retry doomed, so precedence
    keeps it from being selected."""
    plan = plan_for("grounded-mixed-cause")

    assert plan.cause is Cause.EXPIRED_CREDENTIAL
    assert plan.action != RETRY_NOW


def test_a_resource_diagnosis_selects_the_reclaim_action():
    plan = plan_for("grounded-disk-only")

    assert plan.decision is Decision.ACT
    assert plan.cause is Cause.RESOURCE_EXHAUSTION
    assert plan.action == RECLAIM_SPACE


# --- no match escalates rather than guessing -----------------------------


def test_a_policy_rejection_escalates_because_no_code_can_fix_it():
    """The cause is classified confidently and correctly, and there is still
    no action. Re-queueing a post the platform refused is worse than doing
    nothing, so the registry has nothing registered against it."""
    plan = plan_for("grounded-policy-rejection")

    assert plan.decision is Decision.ESCALATE
    assert plan.cause is Cause.POLICY_REJECTION
    assert plan.action is None
    assert "policy_rejection" in plan.reason


def test_a_fault_no_rule_recognises_escalates_rather_than_defaulting_to_retry():
    """A perfectly good diagnosis of a failure this system has no rule for.
    The tempting default is 'probably transient, re-queue it' — which is wrong
    in exactly the cases that matter, so it is not the default."""
    plan = plan_for("grounded-unrecognised-fault")

    assert plan.decision is Decision.ESCALATE
    assert plan.cause is Cause.UNKNOWN
    assert plan.action is None
    assert "no rule recognised" in plan.reason


def test_an_ungrounded_diagnosis_escalates_and_never_acts():
    """The worst outcome available to this design is acting on a fact the
    model made up. ``is_actionable`` is the gate and it is checked first."""
    client = RecordedClient("fabricated-token-claim")
    diagnosis = DiagnosisEngine(client=client).diagnose(client.bundle)
    assert diagnosis.status is DiagnosisStatus.UNGROUNDED

    plan = Executor(registry=default_registry(), capabilities=FULLY_CAPABLE).plan(
        diagnosis, client.bundle
    )
    assert plan.decision is Decision.ESCALATE
    assert plan.action is None
    assert "ungrounded" in plan.reason


def test_an_unavailable_diagnosis_escalates_and_never_acts():
    """The model being down tells us nothing about the estate. Selecting an
    action off that would be acting on our own blindness."""
    bundle = load_bundle("bundle-disk-cascade")
    diagnosis = DiagnosisEngine(client=RaisingClient()).diagnose(bundle)
    assert diagnosis.status is DiagnosisStatus.UNAVAILABLE

    plan = Executor(registry=default_registry(), capabilities=FULLY_CAPABLE).plan(diagnosis, bundle)
    assert plan.decision is Decision.ESCALATE
    assert plan.action is None


def test_cited_evidence_that_was_not_supplied_escalates():
    """Selection resolves the ids the diagnosis rests on against the evidence
    it is handed. A caller passing the wrong bundle gets an escalation, not an
    action chosen from whatever happened to be left."""
    diagnosis, evidence = diagnose("grounded-transient-5xx")
    other = [e for e in evidence if e.surface != "metricool:api/publish"]

    plan = Executor(registry=default_registry(), capabilities=FULLY_CAPABLE).plan(diagnosis, other)
    assert plan.decision is Decision.ESCALATE
    assert "not supplied" in plan.reason


def test_an_action_without_its_capability_wired_escalates():
    """A registered action whose capability is missing is an action that
    cannot run. Reporting a plan we cannot execute is the heartbeat problem
    again, one layer up."""
    plan = plan_for("grounded-transient-5xx", capabilities=Capabilities())

    assert plan.decision is Decision.ESCALATE
    assert plan.action is None
    assert "requeue" in plan.reason


# --- confidence is a precondition, not decoration ------------------------


def test_a_diagnosis_resting_on_a_schedulers_word_cannot_trigger_an_action():
    """``grounded-disk-cascade`` claims 0.7 and is capped to 0.4 by the
    ``REPORTED`` evidence it leans on. Every action floor is above that, so the
    cap earned in DM1.5 does real work here rather than being a number in a
    report."""
    diagnosis, evidence = diagnose("grounded-disk-cascade")
    assert diagnosis.claimed_confidence == pytest.approx(0.7)
    assert diagnosis.confidence == pytest.approx(0.4)

    plan = Executor(registry=default_registry(), capabilities=FULLY_CAPABLE).plan(
        diagnosis, evidence
    )
    assert plan.decision is Decision.ESCALATE
    assert "confidence" in plan.reason


def test_every_action_floor_is_above_the_reported_ceiling():
    """Stated as an invariant so a future action cannot be added with a floor
    low enough for a scheduler's self-report to clear it."""
    from deadman.diagnose.grounding import _CEILING_BY_METHOD
    from deadman.evidence.model import Method

    reported = _CEILING_BY_METHOD[Method.REPORTED]
    assert all(a.min_confidence > reported for a in default_registry().actions())
