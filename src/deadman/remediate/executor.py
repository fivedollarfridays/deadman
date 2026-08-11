"""Selection and execution: the layer that is allowed to touch things.

Two decisions and no third. Either a registered action answers the cause the
cited evidence establishes, at a confidence the cited evidence can carry, with
the capability it needs wired — or the whole thing escalates to a human. There
is no "best effort", because the failure mode being designed against is a
system that does *something* when it does not know what is wrong.

Everything that can refuse, refuses:

* the diagnosis was not grounded, so acting on it would be acting on a fact the
  model invented;
* the evidence it cited was not supplied, so we cannot see what it saw;
* no rule recognised the failure;
* the cause is recognised and no safe automated response exists;
* the confidence the evidence can carry is under the action's floor;
* the capability the action needs is not wired up.

**Dry run is the default.** Selection, classification and reporting all happen;
the action body does not. A caller that wants to move real infrastructure has
to say so, because that is the direction that cannot be undone.

**A plan is the same object either way.** ``execute(dry_run=True)`` returns
exactly the plan a wet run would carry out — otherwise a rehearsal is
documentation, and this project's whole argument is against reports that stand
in for the thing they describe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from deadman.diagnose.schema import Diagnosis, evidence_id
from deadman.evidence.model import Evidence
from deadman.remediate.cause import Cause, classify
from deadman.remediate.registry import (
    Action,
    ActionContext,
    ActionResult,
    Capabilities,
    Registry,
)

logger = logging.getLogger(__name__)


class Decision(str, Enum):
    """Act, or hand it to a human. Nothing in between."""

    ACT = "act"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class RemediationPlan:
    """What will be done and why, decided before anything is done."""

    decision: Decision
    cause: Cause
    reason: str
    """Plain words, whichever way it went. An escalation that does not say what
    stopped it is an alert a human cannot act on."""

    action: str | None
    intent: str | None
    evidence_ids: tuple[str, ...]
    confidence: float
    diagnosis_status: str


@dataclass(frozen=True)
class Remediation:
    """The plan, whether it was carried out, and what happened if it was."""

    plan: RemediationPlan
    dry_run: bool
    result: ActionResult | None
    """``None`` on a dry run and on every escalation. Never a stand-in for
    success — see :class:`~deadman.remediate.registry.ActionResult`."""


def _resolve(
    diagnosis: Diagnosis, evidence: list[Evidence]
) -> tuple[list[Evidence], tuple[str, ...]]:
    """The cited evidence, plus any id we were asked about and not handed."""
    by_id = {evidence_id(e): e for e in evidence}
    cited = [by_id[i] for i in diagnosis.evidence_ids if i in by_id]
    missing = tuple(i for i in diagnosis.evidence_ids if i not in by_id)
    return cited, missing


@dataclass(frozen=True)
class Executor:
    """Turns a diagnosis into a plan, and — only when asked — into an action."""

    registry: Registry
    capabilities: Capabilities = Capabilities()

    def plan(self, diagnosis: Diagnosis, evidence: list[Evidence]) -> RemediationPlan:
        """Decide. Pure: reads, classifies, and touches nothing."""
        cited, missing = _resolve(diagnosis, evidence)
        cause = Cause.UNKNOWN if missing else classify(cited)
        action = self.registry.for_cause(cause)

        refusal = self._refusal(diagnosis, missing, cause, action)
        if refusal is not None or action is None:
            return self._plan(diagnosis, Decision.ESCALATE, cause, refusal or "", None)

        return self._plan(
            diagnosis,
            Decision.ACT,
            cause,
            f"cause {cause.value} is answered by {action.name!r}; confidence "
            f"{diagnosis.confidence} clears its floor of {action.min_confidence}",
            action,
        )

    def _refusal(
        self,
        diagnosis: Diagnosis,
        missing: tuple[str, ...],
        cause: Cause,
        action: Action | None,
    ) -> str | None:
        """Why this must not be acted on, or ``None`` if nothing stops it."""
        if not diagnosis.is_actionable:
            return (
                f"diagnosis is {diagnosis.status.value}: nothing may be selected from a "
                f"hypothesis the system did not verify"
            )
        if missing:
            return (
                f"cited evidence {', '.join(missing)} was not supplied, so the "
                f"basis for the diagnosis cannot be read"
            )
        if cause is Cause.UNKNOWN:
            return "no rule recognised this failure; guessing an action is the thing to avoid"
        if action is None:
            return (
                f"no action is registered for cause {cause.value}; it has no safe "
                f"automated response and belongs with a human"
            )
        if diagnosis.confidence < action.min_confidence:
            return (
                f"confidence {diagnosis.confidence} is under {action.name!r}'s floor of "
                f"{action.min_confidence}; the cited evidence cannot carry this action"
            )
        if getattr(self.capabilities, action.requires) is None:
            return (
                f"{action.name!r} needs the {action.requires!r} capability and this "
                f"deployment has not been given it"
            )
        return None

    def _plan(
        self,
        diagnosis: Diagnosis,
        decision: Decision,
        cause: Cause,
        reason: str,
        action: Action | None,
    ) -> RemediationPlan:
        return RemediationPlan(
            decision=decision,
            cause=cause,
            reason=reason,
            action=action.name if action else None,
            intent=action.intent if action else None,
            evidence_ids=diagnosis.evidence_ids,
            confidence=diagnosis.confidence,
            diagnosis_status=diagnosis.status.value,
        )

    def execute(
        self,
        diagnosis: Diagnosis,
        evidence: list[Evidence],
        *,
        dry_run: bool = True,
    ) -> Remediation:
        """Plan, then carry it out only if asked and only if it was an ACT."""
        plan = self.plan(diagnosis, evidence)
        if dry_run or plan.decision is not Decision.ACT:
            if plan.decision is Decision.ESCALATE:
                logger.warning("escalating: %s", plan.reason)
            return Remediation(plan=plan, dry_run=dry_run, result=None)

        action = self.registry.for_cause(plan.cause)
        cited, _ = _resolve(diagnosis, evidence)
        context = ActionContext(
            diagnosis=diagnosis,
            evidence=tuple(cited),
            cause=plan.cause,
            capabilities=self.capabilities,
        )
        return Remediation(plan=plan, dry_run=False, result=_run(action, context))


def _run(action: Action, context: ActionContext) -> ActionResult:
    """Execute one action under the never-raise contract.

    Same shape as :func:`deadman.probes.base.run_probe`, for the same reason: a
    remediation that blows up must not take down the sweep that selected it,
    and it must not be mistaken for one that worked.
    """
    try:
        return action.run(context)
    except Exception as exc:  # noqa: BLE001 — containment is the point
        logger.warning("action %s raised: %r", action.name, exc)
        return ActionResult(
            action=action.name,
            performed=False,
            detail={"error": f"{type(exc).__name__}: {exc}"},
        )
