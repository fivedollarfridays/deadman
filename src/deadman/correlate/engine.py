"""Inferring the graph: co-occurrence proposes, cited evidence disposes.

The whole task in one sentence. :mod:`deadman.correlate.window` says which
faults are worth one question. This module asks it, and then refuses to accept
the answer as a relationship unless the answer is *tied to more than one
faulting surface by quoted evidence*.

That gate is the entire difference between correlation and coincidence. A model
handed three broken things will happily narrate a single story about them; the
story is free, and a monitor that reports free stories as incidents is worse
than no monitor. So membership in an incident is read off the citations, never
off the window: the surfaces the shared cause actually reaches, established the
same way every other fact in this system is established — quoted verbatim out
of the evidence it is attributed to, per
:mod:`deadman.diagnose.grounding`.

Nothing new is asked of the model, deliberately. The diagnosis prompt already
asks for one causal hypothesis over a pile of evidence, which is exactly the
question correlation needs answered; a second prompt would be a second thing to
keep grounded and a second ``PROMPT_VERSION`` to keep honest for no gain.

Three outcomes, mirroring the layer below:

``CORRELATED``
    A shared cause reaches two or more faulting surfaces on quoted evidence.

``UNCORRELATED``
    We got an answer and it established no cross-surface relationship — it
    reached one surface, or it was rejected for asserting something it was not
    given. This is never a finding that the faults are independent.

``UNAVAILABLE``
    No usable answer. We learned nothing about whether they are related.

**The single isolated fault never gets here at all.** It fails candidacy, so no
prompt is rendered and no model is called. That AC is enforced by absence,
which is the only enforcement that cannot be argued around later.
"""

from __future__ import annotations

from dataclasses import dataclass

from deadman.correlate.incident import Basis, CorrelationStatus, Incident
from deadman.correlate.window import DEFAULT_WINDOW_SECONDS, Candidate, candidates
from deadman.diagnose.engine import DiagnosisEngine
from deadman.diagnose.schema import Diagnosis, DiagnosisStatus, evidence_id
from deadman.evidence.model import Evidence, Observation

#: A correlation is a claim about a relationship, so it takes two things to be
#: about. Not two rows — two surfaces, both actually faulting: a blind row
#: cannot corroborate anything, and one surface cited twice is one surface.
MIN_CORRELATED_SURFACES = 2


@dataclass(frozen=True)
class Correlator:
    """Turns co-occurring faults into at most one incident each."""

    diagnosis: DiagnosisEngine
    window_seconds: float = DEFAULT_WINDOW_SECONDS

    def correlate(self, evidence: list[Evidence]) -> list[Incident]:
        """Every candidate group, resolved. An empty list means nothing
        co-occurred across surfaces — not that nothing is wrong."""
        return [
            self._resolve(candidate)
            for candidate in candidates(evidence, window_seconds=self.window_seconds)
        ]

    def _resolve(self, candidate: Candidate) -> Incident:
        rows = list(candidate.evidence)
        diagnosis = self.diagnosis.diagnose(rows)

        if diagnosis.status is DiagnosisStatus.UNAVAILABLE:
            return _unestablished(
                candidate,
                diagnosis,
                CorrelationStatus.UNAVAILABLE,
                "the diagnosis layer could not be consulted, so whether these faults "
                "share a cause is unknown — not answered in the negative",
            )

        if diagnosis.status is DiagnosisStatus.UNGROUNDED:
            return _unestablished(
                candidate,
                diagnosis,
                CorrelationStatus.UNCORRELATED,
                "the shared-cause hypothesis was rejected for asserting something the "
                "evidence does not support: " + "; ".join(diagnosis.rejected_claims),
            )

        linked = _linked_surfaces(diagnosis, rows)
        if len(linked) < MIN_CORRELATED_SURFACES:
            reached = _names(linked) or "no faulting surface"
            return _unestablished(
                candidate,
                diagnosis,
                CorrelationStatus.UNCORRELATED,
                f"the hypothesis is grounded but reaches {reached}; a relationship "
                f"takes {MIN_CORRELATED_SURFACES} surfaces and co-occurrence is not one",
            )

        return Incident(
            status=CorrelationStatus.CORRELATED,
            basis=Basis.INFERRED,
            surfaces=linked,
            candidate_surfaces=_all_surfaces(candidate),
            shared_cause=diagnosis.hypothesis,
            confidence=diagnosis.confidence,
            claimed_confidence=diagnosis.claimed_confidence,
            unexplained=_unexplained(candidate, linked, diagnosis, rows),
            reason=(
                f"co-occurring faults on {_names(linked)} are tied together by evidence "
                f"cited from each; the relationship was inferred, not traversed"
            ),
            evidence_ids=diagnosis.evidence_ids,
            diagnosis=diagnosis,
        )


def _linked_surfaces(diagnosis: Diagnosis, rows: list[Evidence]) -> tuple[str, ...]:
    """The faulting surfaces the hypothesis actually reaches.

    Blind rows may be cited — the model is instructed to reason about them, and
    :func:`~deadman.diagnose.grounding.confidence_ceiling` already caps what a
    claim leaning on one may be held at — but they are not members. A surface
    we could not see is not a surface we found broken.
    """
    by_id = {evidence_id(e): e for e in rows}
    cited = (by_id[i] for i in diagnosis.evidence_ids if i in by_id)
    return tuple(sorted({e.surface for e in cited if e.observation is Observation.FAULT}))


def _cited_surfaces(diagnosis: Diagnosis, rows: list[Evidence]) -> set[str]:
    by_id = {evidence_id(e): e for e in rows}
    return {by_id[i].surface for i in diagnosis.evidence_ids if i in by_id}


def _all_surfaces(candidate: Candidate) -> tuple[str, ...]:
    return tuple(sorted({e.surface for e in candidate.evidence}))


def _unexplained(
    candidate: Candidate,
    linked: tuple[str, ...],
    diagnosis: Diagnosis,
    rows: list[Evidence],
) -> tuple[str, ...]:
    """What the window swept in that the shared cause does not account for.

    A surface the model *cited* but which is not a member — a blind row it
    reasoned about — still counts as accounted for; it was looked at and
    written about. A surface nobody mentioned did not get that, and it is the
    one most likely to be the next outage.
    """
    accounted = set(linked) | _cited_surfaces(diagnosis, rows)
    return tuple(s for s in _all_surfaces(candidate) if s not in accounted)


def _unestablished(
    candidate: Candidate,
    diagnosis: Diagnosis,
    status: CorrelationStatus,
    reason: str,
) -> Incident:
    """No relationship, everything still reported.

    The faults were real and simultaneous. Returning nothing would erase that,
    so the incident comes back with no members, no confidence, and every
    surface in the window listed as unexplained — which is exactly what is
    true.
    """
    surfaces = _all_surfaces(candidate)
    return Incident(
        status=status,
        basis=Basis.INFERRED,
        surfaces=(),
        candidate_surfaces=surfaces,
        shared_cause=diagnosis.hypothesis,
        confidence=0.0,
        claimed_confidence=diagnosis.claimed_confidence,
        unexplained=surfaces,
        reason=reason,
        evidence_ids=(),
        diagnosis=diagnosis,
    )


def _names(surfaces: tuple[str, ...]) -> str:
    return ", ".join(surfaces)
