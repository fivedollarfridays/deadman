"""Execution: dry run, side effects, and the guard on where action code comes from."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from recordings import RecordedClient

from deadman.diagnose.engine import DiagnosisEngine
from deadman.remediate.actions import default_registry
from deadman.remediate.cause import Cause
from deadman.remediate.executor import Decision, Executor
from deadman.remediate.registry import (
    Action,
    ActionContext,
    ActionResult,
    Capabilities,
    NonDeterministicAction,
    Registry,
)

PERFORMED: list[str] = []


def record_it(context: ActionContext) -> ActionResult:
    """A deterministic action body, defined in this file like every real one."""
    PERFORMED.append(context.cause.value)
    return ActionResult(action="record-it", performed=True, detail={"calls": len(PERFORMED)})


def explode(context: ActionContext) -> ActionResult:
    raise RuntimeError("the remediation endpoint refused the connection")


def registry_with(run, name: str = "record-it") -> Registry:
    registry = Registry()
    registry.register(
        Action(
            name=name,
            cause=Cause.TRANSIENT_UPSTREAM,
            intent="record that this ran",
            requires="requeue",
            min_confidence=0.5,
            run=run,
        )
    )
    return registry


@pytest.fixture(autouse=True)
def _clear_side_effects():
    PERFORMED.clear()
    yield
    PERFORMED.clear()


@pytest.fixture
def transient():
    client = RecordedClient("grounded-transient-5xx")
    return DiagnosisEngine(client=client).diagnose(client.bundle), client.bundle


def executor_for(run) -> Executor:
    return Executor(
        registry=registry_with(run),
        capabilities=Capabilities(requeue=lambda surface: True),
    )


# --- dry run -------------------------------------------------------------


def test_dry_run_selects_and_reports_without_touching_anything(transient):
    diagnosis, evidence = transient
    outcome = executor_for(record_it).execute(diagnosis, evidence, dry_run=True)

    assert PERFORMED == [], "dry run must not execute the action body"
    assert outcome.dry_run is True
    assert outcome.result is None
    assert outcome.plan.decision is Decision.ACT
    assert outcome.plan.action == "record-it"
    assert outcome.plan.intent == "record that this ran"
    assert outcome.plan.cause is Cause.TRANSIENT_UPSTREAM
    assert outcome.plan.evidence_ids, "the plan reports what it rests on"


def test_dry_run_is_the_default(transient):
    """Fail closed. Taking a real action on infrastructure is the direction
    that cannot be undone, so it has to be asked for explicitly."""
    diagnosis, evidence = transient
    outcome = executor_for(record_it).execute(diagnosis, evidence)

    assert outcome.dry_run is True
    assert PERFORMED == []


def test_a_wet_run_actually_executes_the_action(transient):
    diagnosis, evidence = transient
    outcome = executor_for(record_it).execute(diagnosis, evidence, dry_run=False)

    assert PERFORMED == ["transient_upstream"]
    assert outcome.result is not None
    assert outcome.result.performed is True


def test_the_plan_is_identical_whether_or_not_it_is_executed(transient):
    """Dry run has to report the plan that a real run would take, or it is
    documentation rather than a rehearsal."""
    diagnosis, evidence = transient
    executor = executor_for(record_it)

    assert executor.execute(diagnosis, evidence, dry_run=True).plan == (
        executor.execute(diagnosis, evidence, dry_run=False).plan
    )


def test_planning_alone_never_executes(transient):
    diagnosis, evidence = transient
    executor_for(record_it).plan(diagnosis, evidence)

    assert PERFORMED == []


def test_an_escalation_executes_nothing_even_on_a_wet_run(transient):
    diagnosis, evidence = transient
    executor = Executor(registry=registry_with(record_it), capabilities=Capabilities())

    outcome = executor.execute(diagnosis, evidence, dry_run=False)

    assert outcome.plan.decision is Decision.ESCALATE
    assert outcome.result is None
    assert PERFORMED == []


# --- an action that fails is contained -----------------------------------


def test_an_action_that_raises_is_contained_not_propagated(transient):
    """Same contract as ``run_probe``. A remediation blowing up must not take
    down the sweep that selected it, and it must not be mistaken for one that
    worked."""
    diagnosis, evidence = transient
    outcome = executor_for(explode).execute(diagnosis, evidence, dry_run=False)

    assert outcome.result is not None
    assert outcome.result.performed is False
    assert "RuntimeError" in outcome.result.detail["error"]


def test_an_action_result_does_not_claim_the_fault_is_fixed():
    """Guarding the seam DM1.7 owns. ``performed`` is a fact about the
    executor; whether the surface recovered is a fact about the surface, and
    only a fresh observation may say so."""
    fields = set(inspect.signature(ActionResult).parameters)

    assert fields == {"action", "performed", "detail"}
    assert not {"success", "fixed", "resolved", "verified"} & fields


# --- action bodies are code on disk --------------------------------------


def test_a_runtime_generated_action_body_cannot_be_registered():
    """The literal acceptance criterion. A body built by ``exec`` has no
    source file behind it, and the registry refuses it."""
    namespace: dict = {}
    exec("def generated(context):\n    return None", namespace)  # noqa: S102

    with pytest.raises(NonDeterministicAction, match="not defined in a source file"):
        registry_with(namespace["generated"], name="generated")


def test_every_shipped_action_body_lives_in_this_package():
    remediate = Path(inspect.getfile(default_registry)).parent

    for action in default_registry().actions():
        source = Path(inspect.getsourcefile(action.run))
        assert source.is_file()
        assert source.parent == remediate, f"{action.name} is defined outside the package"


def test_an_action_requiring_a_capability_that_does_not_exist_is_refused():
    """A typo in ``requires`` would silently mean 'needs nothing', and the
    action would be selected with no way to do its job."""
    registry = Registry()
    action = Action(
        name="typo",
        cause=Cause.TRANSIENT_UPSTREAM,
        intent="…",
        requires="requeu",
        min_confidence=0.5,
        run=record_it,
    )
    with pytest.raises(ValueError, match="capability"):
        registry.register(action)


def test_two_actions_cannot_claim_the_same_cause():
    """Selection has to be a function. Two candidates for one cause means the
    choice falls to registration order, which is not a decision anyone made."""
    registry = registry_with(record_it)
    with pytest.raises(ValueError, match="already"):
        registry.register(
            Action(
                name="other",
                cause=Cause.TRANSIENT_UPSTREAM,
                intent="…",
                requires="requeue",
                min_confidence=0.5,
                run=record_it,
            )
        )


def test_no_action_is_registered_against_an_unknown_cause():
    """UNKNOWN exists to mean 'we did not recognise this'. An action behind it
    would be the guess the acceptance criteria forbid."""
    assert default_registry().for_cause(Cause.UNKNOWN) is None
