"""The verification loop: the layer that is allowed to say "fixed".

``ActionResult.performed`` (DM1.6) is a fact about this process — the code ran
and did not raise. It is never a fact about the surface, and nothing here may
read it as one. The only thing that may say a fault is gone is a fresh
:class:`~deadman.evidence.model.Observation.HEALTHY` read off the same probe
that reported the fault, taken *after* the remediation ran.

**"Cannot be re-observed" is not "fixed".** If the probe itself goes blind on
re-run — the same never-raise contract as detection, via
:func:`~deadman.probes.base.run_probe` — that is ``UNOBSERVABLE``, not
``HEALTHY``, and the loop reports the fix unverified rather than successful.
Blindness about whether a fix worked is exactly as dangerous as blindness
about the original fault; collapsing it into a quiet success would smuggle
the heartbeat problem back in through the repair path.

**Repeated failure stops.** Each attempt re-plans and re-executes against the
*same* diagnosis and evidence — the world may have changed underneath the
action even though the inputs did not — but only up to ``max_attempts``. A
surface that stays broken after the cap is reported ``EXHAUSTED``, not
retried forever.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from deadman.diagnose.schema import Diagnosis
from deadman.evidence.model import Evidence, Observation
from deadman.probes.base import Probe, run_probe
from deadman.remediate.executor import Decision, Executor, Remediation


class VerificationStatus(str, Enum):
    """What the loop can honestly conclude. Three states, not two — a plain
    boolean would erase the difference between "never tried" and "tried and
    failed", and an operator needs to know which one happened."""

    VERIFIED = "verified"
    """A fresh re-observation of the originating probe came back ``HEALTHY``."""

    NOT_ATTEMPTED = "not_attempted"
    """The executor never reached ``ACT`` — it escalated on the first plan, so
    nothing changed and there is nothing to verify."""

    EXHAUSTED = "exhausted"
    """At least one remediation ran and was re-observed, and none of the
    attempts, up to ``max_attempts``, came back ``HEALTHY``."""


@dataclass(frozen=True)
class Attempt:
    """One trip through the loop: what was done, and what looking again found."""

    remediation: Remediation
    reobservation: Evidence | None
    """``None`` only when the remediation escalated — there is nothing to
    re-observe when nothing was done."""


@dataclass(frozen=True)
class VerificationOutcome:
    """The full history of the loop and the one honest verdict at the end."""

    status: VerificationStatus
    attempts: tuple[Attempt, ...]

    @property
    def verified(self) -> bool:
        return self.status is VerificationStatus.VERIFIED


def _surfaces(diagnosis: Diagnosis) -> set[str]:
    return {evidence_id.rsplit("#", 1)[0] for evidence_id in diagnosis.evidence_ids}


def verify_remediation(
    executor: Executor,
    probe: Probe,
    diagnosis: Diagnosis,
    evidence: list[Evidence],
    *,
    max_attempts: int = 3,
) -> VerificationOutcome:
    """Remediate, then prove it — up to ``max_attempts`` times.

    ``probe`` must be the one that originated the fault this diagnosis rests
    on: its surface has to appear among the evidence the diagnosis cited.
    Verifying against any other probe would prove nothing about the fault
    that was actually acted on, so this refuses rather than guessing.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be at least 1, got {max_attempts}")
    if probe.surface not in _surfaces(diagnosis):
        raise ValueError(
            f"probe {probe.surface!r} is not among the surfaces diagnosis cited "
            f"({sorted(_surfaces(diagnosis))}); the verification loop re-runs the "
            f"probe that originated the fault, never an unrelated one"
        )

    attempts: list[Attempt] = []
    for _ in range(max_attempts):
        remediation = executor.execute(diagnosis, evidence, dry_run=False)

        if remediation.plan.decision is not Decision.ACT:
            attempts.append(Attempt(remediation=remediation, reobservation=None))
            return VerificationOutcome(
                status=VerificationStatus.NOT_ATTEMPTED, attempts=tuple(attempts)
            )

        reobservation = run_probe(probe)
        attempts.append(Attempt(remediation=remediation, reobservation=reobservation))
        if reobservation.observation is Observation.HEALTHY:
            return VerificationOutcome(status=VerificationStatus.VERIFIED, attempts=tuple(attempts))

    return VerificationOutcome(status=VerificationStatus.EXHAUSTED, attempts=tuple(attempts))
