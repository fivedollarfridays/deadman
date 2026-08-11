"""The verification loop: closing the honesty gap between "ran" and "fixed".

An ``ActionResult`` says only that a code path executed without raising
(DM1.6). Nothing here may treat that as a fix. The only thing that may is a
fresh re-observation of the surface the fault was reported on — this module
re-runs the originating probe after every remediation attempt and requires it
to come back ``HEALTHY`` before saying so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from recordings import RecordedClient

from deadman.diagnose.engine import DiagnosisEngine
from deadman.evidence.model import Evidence, Method, Observation
from deadman.remediate.cause import Cause
from deadman.remediate.executor import Decision, Executor
from deadman.remediate.registry import Action, ActionContext, ActionResult, Capabilities, Registry
from deadman.remediate.verify import VerificationStatus, verify_remediation

PERFORMED: list[str] = []


def record_it(context: ActionContext) -> ActionResult:
    PERFORMED.append(context.cause.value)
    return ActionResult(action="record-it", performed=True, detail={})


@pytest.fixture(autouse=True)
def _clear_side_effects():
    PERFORMED.clear()
    yield
    PERFORMED.clear()


def registry_with(run) -> Registry:
    registry = Registry()
    registry.register(
        Action(
            name="record-it",
            cause=Cause.TRANSIENT_UPSTREAM,
            intent="record that this ran",
            requires="requeue",
            min_confidence=0.5,
            run=run,
        )
    )
    return registry


def executor_for(run, capable: bool = True) -> Executor:
    capabilities = Capabilities(requeue=lambda surface: True) if capable else Capabilities()
    return Executor(registry=registry_with(run), capabilities=capabilities)


@pytest.fixture
def transient():
    """A grounded, actionable diagnosis citing ``metricool:fwtx_dao`` and
    ``metricool:api/publish``. Same fixture ``test_remediate_executor.py``
    exercises the executor's own behaviour against."""
    client = RecordedClient("grounded-transient-5xx")
    return DiagnosisEngine(client=client).diagnose(client.bundle), client.bundle


ORIGINATING_SURFACE = "metricool:fwtx_dao"


def _evidence(observation: Observation, surface: str = ORIGINATING_SURFACE) -> Evidence:
    return Evidence(
        surface=surface,
        observation=observation,
        method=Method.DESTINATION_PUBLIC,
        summary="reobserved",
        source="GET https://x.com/fwtx_dao/status/8891",
    )


@dataclass
class ScriptedProbe:
    """A fake probe returning one queued :class:`Evidence` per call.

    Standing in for a real :class:`~deadman.probes.base.Probe` so the loop's
    behaviour can be pinned without a live surface — the same substitution
    ``RecordedClient`` makes for the model.
    """

    surface: str
    script: list[Evidence] = field(default_factory=list)
    question: str = "did the fix land?"
    calls: int = 0

    def observe(self) -> Evidence:
        self.calls += 1
        return self.script.pop(0)


@dataclass
class RaisingProbe:
    surface: str
    question: str = "did the fix land?"
    calls: int = 0

    def observe(self) -> Evidence:
        self.calls += 1
        raise ConnectionError("the destination is unreachable")


# --- success requires a fresh HEALTHY observation -------------------------


def test_a_verified_fix_re_runs_the_probe_and_requires_healthy(transient):
    diagnosis, evidence = transient
    probe = ScriptedProbe(surface=ORIGINATING_SURFACE, script=[_evidence(Observation.HEALTHY)])

    outcome = verify_remediation(executor_for(record_it), probe, diagnosis, evidence)

    assert probe.calls == 1, "the originating probe must be re-run after remediation"
    assert outcome.status is VerificationStatus.VERIFIED
    assert outcome.verified is True
    assert outcome.attempts[-1].reobservation.observation is Observation.HEALTHY


def test_the_executors_own_return_value_is_never_sufficient(transient):
    """The action ran and reported ``performed=True`` on every attempt; the
    probe never comes back healthy. That must not read as success."""
    diagnosis, evidence = transient
    probe = ScriptedProbe(
        surface=ORIGINATING_SURFACE,
        script=[_evidence(Observation.FAULT) for _ in range(3)],
    )

    outcome = verify_remediation(
        executor_for(record_it), probe, diagnosis, evidence, max_attempts=3
    )

    assert all(a.remediation.result.performed for a in outcome.attempts)
    assert outcome.verified is False
    assert outcome.status is not VerificationStatus.VERIFIED


def test_a_fix_that_cannot_be_reobserved_is_unverified_not_successful(transient):
    """The probe itself goes blind after remediation. ``run_probe`` contains
    the raise as ``UNOBSERVABLE`` (never ``FAULT``) — and blind is still not a
    fix, so the loop must not report success either."""
    diagnosis, evidence = transient
    probe = RaisingProbe(surface=ORIGINATING_SURFACE)

    outcome = verify_remediation(
        executor_for(record_it), probe, diagnosis, evidence, max_attempts=1
    )

    assert outcome.verified is False
    assert outcome.attempts[-1].reobservation.observation is Observation.UNOBSERVABLE


# --- repeated failure stops rather than looping ----------------------------


def test_repeated_failed_remediation_stops_after_the_attempt_cap(transient):
    diagnosis, evidence = transient
    probe = ScriptedProbe(
        surface=ORIGINATING_SURFACE,
        script=[_evidence(Observation.FAULT) for _ in range(3)],
    )

    outcome = verify_remediation(
        executor_for(record_it), probe, diagnosis, evidence, max_attempts=3
    )

    assert probe.calls == 3
    assert len(outcome.attempts) == 3
    assert outcome.status is VerificationStatus.EXHAUSTED
    assert PERFORMED == ["transient_upstream"] * 3


def test_a_late_success_stops_the_loop_immediately(transient):
    """Verification must not keep hammering a surface once it is healthy."""
    diagnosis, evidence = transient
    probe = ScriptedProbe(
        surface=ORIGINATING_SURFACE,
        script=[_evidence(Observation.FAULT), _evidence(Observation.HEALTHY)],
    )

    outcome = verify_remediation(
        executor_for(record_it), probe, diagnosis, evidence, max_attempts=5
    )

    assert probe.calls == 2
    assert len(outcome.attempts) == 2
    assert outcome.status is VerificationStatus.VERIFIED


def test_max_attempts_must_be_at_least_one(transient):
    diagnosis, evidence = transient
    probe = ScriptedProbe(surface=ORIGINATING_SURFACE, script=[])

    with pytest.raises(ValueError, match="max_attempts"):
        verify_remediation(executor_for(record_it), probe, diagnosis, evidence, max_attempts=0)


# --- an escalation has nothing to verify -----------------------------------


def test_an_escalation_is_not_attempted_and_the_probe_is_never_called(transient):
    diagnosis, evidence = transient
    probe = ScriptedProbe(surface=ORIGINATING_SURFACE, script=[])
    executor = executor_for(record_it, capable=False)  # capability missing -> escalate

    outcome = verify_remediation(executor, probe, diagnosis, evidence, max_attempts=3)

    assert probe.calls == 0
    assert PERFORMED == []
    assert outcome.status is VerificationStatus.NOT_ATTEMPTED
    assert outcome.verified is False
    assert outcome.attempts[-1].remediation.plan.decision is Decision.ESCALATE
    assert outcome.attempts[-1].reobservation is None


# --- the probe has to be the one the diagnosis is actually about -----------


def test_verifying_against_an_unrelated_surface_is_refused(transient):
    diagnosis, evidence = transient
    probe = ScriptedProbe(surface="host:mac/disk", script=[])

    with pytest.raises(ValueError, match="host:mac/disk"):
        verify_remediation(executor_for(record_it), probe, diagnosis, evidence)

    assert probe.calls == 0
