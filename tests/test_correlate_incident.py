"""The invariants an ``Incident`` refuses to be constructed without.

These are belt-and-braces — :mod:`deadman.correlate.engine` cannot currently
violate either — and they are here because the type is what a future caller
will build against, and the two rules are the ones whose violation would be
invisible in a report rather than obvious.
"""

from __future__ import annotations

import pytest

from deadman.correlate.incident import Basis, CorrelationStatus, Incident
from deadman.diagnose.schema import Diagnosis, DiagnosisStatus

BLANK = Diagnosis(
    status=DiagnosisStatus.UNAVAILABLE,
    hypothesis="",
    confidence=0.0,
    claimed_confidence=0.0,
    evidence_ids=(),
    citations=(),
    model="none",
    temperature=0.0,
    prompt_version="diagnose/v1",
)


def build(**overrides) -> Incident:
    fields = {
        "status": CorrelationStatus.CORRELATED,
        "basis": Basis.INFERRED,
        "surfaces": ("host:mac/disk", "metricool:fwtx_dao"),
        "candidate_surfaces": ("host:mac/disk", "metricool:fwtx_dao"),
        "shared_cause": "one volume filled and took the upload worker with it",
        "confidence": 0.4,
        "claimed_confidence": 0.7,
        "unexplained": (),
        "reason": "tied by evidence cited from each",
        "evidence_ids": (),
        "diagnosis": BLANK,
    }
    return Incident(**{**fields, **overrides})


def test_one_surface_is_not_a_relationship():
    with pytest.raises(ValueError, match="at least two surfaces"):
        build(surfaces=("host:mac/disk",))


def test_an_unestablished_incident_cannot_carry_confidence():
    """Confidence in what? Nothing was established. A number here would be a
    number about a relationship the system declined to claim."""
    with pytest.raises(ValueError, match="cannot carry confidence"):
        build(status=CorrelationStatus.UNCORRELATED, surfaces=(), confidence=0.4)


def test_confidence_outside_the_range_is_refused():
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        build(confidence=1.4)
