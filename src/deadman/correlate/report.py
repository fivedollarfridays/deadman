"""Rendering an incident, and the two things the text must never soften.

**It says the relationship was inferred.** Not implied by hedged phrasing —
stated, in a labelled line, naming the surfaces no edge was found between and
saying plainly what inference costs. A reader handed "the disk caused the
publish failure" will act on it as though something declared that edge. Nothing
did, and the difference is the reader's to weigh, not ours to hide.

**It always prints a number.** The failure mode being designed against is a
report that shows confidence when it is flattering and omits it when it is not,
which leaves the reader to supply a number of their own — invariably a
generous one. ``0.00`` gets printed, next to what the model asked for, so the
cap is visible as a cap rather than as a quiet subtraction.

And what the incident does *not* cover is a section, not a footnote. A surface
that co-occurred and went unexplained is the one most likely to be the next
outage.
"""

from __future__ import annotations

from typing import Any

from deadman.correlate.incident import CorrelationStatus, Incident

_NONE = "none — no relationship was established"


def basis_note(incident: Incident) -> str:
    """The inferred-not-traversed statement, about *these* surfaces.

    Interpolated rather than canned, because a fixed sentence stops being read
    after the second report and this one has to keep being read.
    """
    named = " and ".join(incident.surfaces or incident.candidate_surfaces)
    return (
        f"{incident.basis.value}, not traversed. No lineage graph connects {named}, "
        f"so nothing was walked: the relationship was reasoned from co-occurrence in "
        f"time plus evidence quoted out of each surface. It can be wrong in ways a "
        f"declared dependency edge cannot."
    )


def _citation_lines(incident: Incident) -> list[str]:
    return [
        f"  {c.evidence_id}  {c.quote!r}" for c in incident.diagnosis.citations
    ] or ["  (none — the claim rests on nothing that survived grounding)"]


def render(incident: Incident) -> str:
    """The whole incident as text, for a human reading an alert."""
    diagnosis = incident.diagnosis
    surfaces = ", ".join(incident.surfaces) if incident.surfaces else _NONE
    unexplained = incident.unexplained or ("(nothing)",)

    lines = [
        f"INCIDENT — {incident.status.value}",
        f"Surfaces: {surfaces}",
        f"Co-occurred in this window: {', '.join(incident.candidate_surfaces)}",
        "",
        "Hypothesised shared cause:",
        f"  {incident.shared_cause or '(none offered)'}",
        "",
        f"Basis: {basis_note(incident)}",
        "",
        f"Confidence: {incident.confidence:.2f} "
        f"(the model claimed {incident.claimed_confidence:.2f}; capped by the trust "
        f"tier of the weakest evidence cited)",
        f"Why: {incident.reason}",
        "",
        "Not accounted for by this incident:",
        *(f"  - {s}" for s in unexplained),
        "",
        "Cited evidence:",
        *_citation_lines(incident),
        "",
        f"Diagnosis: {diagnosis.model} at temperature {diagnosis.temperature}, "
        f"prompt {diagnosis.prompt_version} ({diagnosis.status.value})",
    ]
    if incident.status is not CorrelationStatus.CORRELATED and diagnosis.rejected_claims:
        lines.extend(["", "Rejected claims:", *(f"  - {r}" for r in diagnosis.rejected_claims)])
    return "\n".join(lines)


def as_dict(incident: Incident) -> dict[str, Any]:
    """The machine-readable form.

    ``basis`` is a first-class key: a consumer must not have to parse prose to
    learn that the relationship was inferred.
    """
    return {
        "status": incident.status.value,
        "basis": incident.basis.value,
        "surfaces": list(incident.surfaces),
        "candidate_surfaces": list(incident.candidate_surfaces),
        "shared_cause": incident.shared_cause,
        "confidence": incident.confidence,
        "claimed_confidence": incident.claimed_confidence,
        "unexplained": list(incident.unexplained),
        "reason": incident.reason,
        "evidence_ids": list(incident.evidence_ids),
        "diagnosis": {
            "status": incident.diagnosis.status.value,
            "model": incident.diagnosis.model,
            "temperature": incident.diagnosis.temperature,
            "prompt_version": incident.diagnosis.prompt_version,
            "citations": [
                {"evidence_id": c.evidence_id, "quote": c.quote}
                for c in incident.diagnosis.citations
            ],
            "rejected_claims": list(incident.diagnosis.rejected_claims),
        },
    }
