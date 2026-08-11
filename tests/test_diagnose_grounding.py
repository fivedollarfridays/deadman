"""Grounding: the rule that the model may infer but may not invent.

These tests are about one boundary. A hypothesis is allowed to be new text —
that is the whole reason a model is here rather than a rule engine. A *fact*
is not. Every fact the model leans on must be quotable, verbatim, out of the
evidence it was handed, or the diagnosis does not survive.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deadman.diagnose.grounding import (
    MIN_QUOTE_CHARS,
    confidence_ceiling,
    corpus_for,
    reject_reason,
)
from deadman.diagnose.schema import Citation, Diagnosis, DiagnosisStatus, evidence_id
from deadman.evidence.model import Evidence, Method, Observation, unobservable

FIXED = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)


def disk_fault() -> Evidence:
    return Evidence(
        surface="host:mac/disk",
        observation=Observation.FAULT,
        method=Method.LOCAL_ARTIFACT,
        summary="free space projected to hit the 10GB floor in 2.1 days",
        source="shutil.disk_usage('/')",
        read_at=FIXED,
        detail={
            "free_gb": 50.2,
            "slope_gb_per_day": -20.0,
            "runway_days": 2.1,
            "raw_note": "docker builds began failing with 'no space left on device'",
        },
    )


def scheduler_claim() -> Evidence:
    return Evidence(
        surface="metricool:fwtx_dao",
        observation=Observation.FAULT,
        method=Method.REPORTED,
        summary="scheduler reports post 8891 published",
        source="metricool api /v1/scheduled",
        read_at=FIXED,
        detail={"post_id": "8891", "status_code": 500},
    )


# --- evidence ids -------------------------------------------------------


def test_evidence_id_is_stable_across_calls():
    assert evidence_id(disk_fault()) == evidence_id(disk_fault())


def test_evidence_id_names_the_surface_so_a_human_can_read_it():
    assert evidence_id(disk_fault()).startswith("host:mac/disk#")


def test_evidence_id_differs_between_two_reads_of_the_same_surface():
    """Two observations of one surface are two facts, not one. Correlation and
    citation both break if a later read can be mistaken for an earlier one."""
    later = Evidence(
        surface="host:mac/disk",
        observation=Observation.FAULT,
        method=Method.LOCAL_ARTIFACT,
        summary="free space projected to hit the 10GB floor in 2.1 days",
        source="shutil.disk_usage('/')",
        read_at=datetime(2026, 8, 11, 4, 0, tzinfo=timezone.utc),
        detail={},
    )
    assert evidence_id(later) != evidence_id(disk_fault())


# --- the searchable corpus ----------------------------------------------


def test_corpus_includes_unstructured_detail_values():
    """`Evidence.detail` is deliberately unstructured — it is the raw failure
    material. If it is not quotable, the model has nothing real to cite."""
    corpus = corpus_for(disk_fault())
    assert "no space left on device" in corpus
    assert "-20.0" in corpus


def test_corpus_includes_detail_keys_not_only_values():
    assert "slope_gb_per_day" in corpus_for(disk_fault())


def test_corpus_includes_summary_source_and_observation():
    corpus = corpus_for(disk_fault())
    assert "10gb floor" in corpus
    assert "shutil.disk_usage" in corpus
    assert "fault" in corpus


# --- rejection ----------------------------------------------------------


def test_verbatim_quote_from_detail_is_accepted():
    by_id = {evidence_id(disk_fault()): disk_fault()}
    claim = Citation(evidence_id=evidence_id(disk_fault()), quote="no space left on device")
    assert reject_reason(claim, by_id) is None


def test_quote_matching_ignores_case_and_whitespace_noise():
    by_id = {evidence_id(disk_fault()): disk_fault()}
    claim = Citation(
        evidence_id=evidence_id(disk_fault()),
        quote="  No Space   Left On Device ",
    )
    assert reject_reason(claim, by_id) is None


def test_fabricated_quote_is_rejected():
    """The centerpiece. Nothing in the disk evidence mentions a token, so the
    model does not get to say one expired."""
    by_id = {evidence_id(disk_fault()): disk_fault()}
    claim = Citation(
        evidence_id=evidence_id(disk_fault()),
        quote="the API token expired on 2026-08-01",
    )
    reason = reject_reason(claim, by_id)
    assert reason is not None
    assert "not present" in reason


def test_quote_from_a_different_piece_of_evidence_is_rejected():
    """Grounding is per-evidence, not corpus-wide. Attributing the scheduler's
    500 to the disk read is a real claim about causation, smuggled in as a
    citation."""
    by_id = {
        evidence_id(disk_fault()): disk_fault(),
        evidence_id(scheduler_claim()): scheduler_claim(),
    }
    claim = Citation(evidence_id=evidence_id(disk_fault()), quote="post 8891 published")
    assert reject_reason(claim, by_id) is not None


def test_unknown_evidence_id_is_rejected():
    by_id = {evidence_id(disk_fault()): disk_fault()}
    claim = Citation(evidence_id="host:mac/disk#deadbeef", quote="runway_days")
    reason = reject_reason(claim, by_id)
    assert reason is not None
    assert "unknown evidence id" in reason


def test_trivially_short_quote_is_rejected():
    """A one-character quote matches nearly any corpus. It is not evidence, it
    is a way of satisfying the citation requirement without citing anything."""
    by_id = {evidence_id(disk_fault()): disk_fault()}
    claim = Citation(evidence_id=evidence_id(disk_fault()), quote="e")
    reason = reject_reason(claim, by_id)
    assert reason is not None
    assert str(MIN_QUOTE_CHARS) in reason


def test_empty_quote_is_rejected():
    by_id = {evidence_id(disk_fault()): disk_fault()}
    assert reject_reason(Citation(evidence_id=evidence_id(disk_fault()), quote=""), by_id)


# --- confidence ceilings -------------------------------------------------


def test_a_diagnosis_resting_on_a_scheduler_report_cannot_be_confident():
    """`Method.REPORTED` is a heartbeat wearing a hat. A model asserting 0.95
    off one is doing exactly what this project exists to stop."""
    assert confidence_ceiling([scheduler_claim()]) < 0.5


def test_a_local_artifact_supports_more_confidence_than_a_report():
    assert confidence_ceiling([disk_fault()]) > confidence_ceiling([scheduler_claim()])


def test_the_weakest_cited_evidence_sets_the_ceiling():
    """A strong read does not launder a weak one it is reasoning alongside."""
    both = confidence_ceiling([disk_fault(), scheduler_claim()])
    assert both == confidence_ceiling([scheduler_claim()])


def test_reasoning_over_a_blind_spot_caps_confidence_hard():
    blind = unobservable("instagram:fwtx_dao", "permalink", "platform is opaque")
    assert confidence_ceiling([disk_fault(), blind]) <= 0.5


def test_no_evidence_means_no_confidence():
    assert confidence_ceiling([]) == 0.0


# --- the Diagnosis type --------------------------------------------------


def test_diagnosis_records_model_temperature_and_prompt_version():
    d = Diagnosis(
        status=DiagnosisStatus.GROUNDED,
        hypothesis="disk exhaustion starved the container runtime",
        confidence=0.6,
        claimed_confidence=0.9,
        evidence_ids=(evidence_id(disk_fault()),),
        citations=(Citation(evidence_id(disk_fault()), "no space left on device"),),
        model="gemini-3.5-flash",
        temperature=0.0,
        prompt_version="diagnose/v1",
    )
    assert (d.model, d.temperature, d.prompt_version) == ("gemini-3.5-flash", 0.0, "diagnose/v1")


def test_only_a_grounded_diagnosis_is_actionable():
    """DM1.6 selects remediations off this flag. An ungrounded hypothesis must
    never reach an executor."""
    common = dict(
        hypothesis="h",
        claimed_confidence=0.9,
        evidence_ids=(),
        citations=(),
        model="m",
        temperature=0.0,
        prompt_version="v",
    )
    grounded = Diagnosis(status=DiagnosisStatus.GROUNDED, confidence=0.6, **common)
    ungrounded = Diagnosis(status=DiagnosisStatus.UNGROUNDED, confidence=0.0, **common)
    unavailable = Diagnosis(status=DiagnosisStatus.UNAVAILABLE, confidence=0.0, **common)

    assert grounded.is_actionable
    assert not ungrounded.is_actionable
    assert not unavailable.is_actionable


def test_a_rejected_diagnosis_cannot_carry_confidence():
    with pytest.raises(ValueError):
        Diagnosis(
            status=DiagnosisStatus.UNGROUNDED,
            hypothesis="h",
            confidence=0.8,
            claimed_confidence=0.8,
            evidence_ids=(),
            citations=(),
            model="m",
            temperature=0.0,
            prompt_version="v",
        )


def test_confidence_outside_the_unit_interval_is_a_schema_error():
    with pytest.raises(ValueError):
        Diagnosis(
            status=DiagnosisStatus.GROUNDED,
            hypothesis="h",
            confidence=1.4,
            claimed_confidence=1.4,
            evidence_ids=(),
            citations=(),
            model="m",
            temperature=0.0,
            prompt_version="v",
        )
