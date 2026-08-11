"""The report: what a human is actually told.

Two acceptance criteria live or die in rendered text rather than in a field —
that the relationship was inferred and not traversed, and that the confidence
is surfaced rather than left to be inferred from tone. So they are asserted
against the string a person reads.
"""

from __future__ import annotations

from recordings import RecordedClient, load_bundle

from deadman.correlate.engine import Correlator
from deadman.correlate.report import as_dict, render
from deadman.diagnose.engine import DiagnosisEngine

CASCADE = "bundle-disk-cascade"


def incident_from(recording: str):
    client = RecordedClient(recording)
    correlator = Correlator(diagnosis=DiagnosisEngine(client=client))
    return correlator.correlate(load_bundle(CASCADE))[0]


# --- inferred, and saying so ----------------------------------------------


def test_the_report_states_the_relationship_was_inferred_not_traversed():
    """AC, verbatim. And not as boilerplate — it names the two surfaces it
    could not find an edge between, so the sentence is about this incident."""
    text = render(incident_from("grounded-disk-cascade"))

    assert "inferred, not traversed" in text
    assert "no lineage graph" in text.lower()
    assert "host:mac/disk" in text and "metricool:fwtx_dao" in text


def test_the_report_says_what_inferred_costs():
    """A reader who is told the claim was inferred and not what that means has
    been given a word, not a caveat."""
    text = render(incident_from("grounded-disk-cascade"))

    assert "co-occurrence" in text
    assert "can be wrong" in text


# --- confidence, surfaced ------------------------------------------------


def test_confidence_is_stated_as_a_number_beside_what_was_claimed():
    """AC: correlation confidence is carried and surfaced, never implied. Both
    numbers, because the gap between 0.70 asked and 0.40 stood behind is the
    part an operator needs — it says the tie runs through a scheduler's own
    report of itself."""
    text = render(incident_from("grounded-disk-cascade"))

    assert "0.40" in text
    assert "0.70" in text
    assert "confidence" in text.lower()


def test_confidence_is_stated_even_when_there_is_none():
    """The failure mode is a report that prints a number when it is flattering
    and omits it otherwise, leaving the reader to supply their own."""
    text = render(incident_from("grounded-disk-only"))

    assert "0.00" in text
    assert "no relationship" in text.lower()


# --- what the incident does not cover ------------------------------------


def test_the_unexplained_surface_is_named_and_not_dressed_as_fine():
    text = render(incident_from("grounded-disk-cascade"))

    assert "sms:relay" in text
    assert "not accounted for" in text.lower()


def test_the_report_carries_the_evidence_the_claim_rests_on():
    """Provenance or it is not a fact. Every quote the hypothesis leaned on,
    against the id it was taken from."""
    text = render(incident_from("grounded-disk-cascade"))

    assert "host:mac/disk#7f8f3eb7" in text
    assert "slope_gb_per_day=-20.0" in text
    assert "gemini-3.5-flash" in text
    assert "diagnose/v1" in text


# --- the machine-readable form -------------------------------------------


def test_the_serialised_form_carries_basis_and_both_numbers():
    """Whatever consumes this over HTTP must not have to parse prose to learn
    the claim was inferred."""
    row = as_dict(incident_from("grounded-disk-cascade"))

    assert row["basis"] == "inferred"
    assert row["status"] == "correlated"
    assert row["confidence"] == 0.4
    assert row["claimed_confidence"] == 0.7
    assert row["unexplained"] == ["sms:relay"]
    assert row["surfaces"] == ["host:mac/disk", "metricool:fwtx_dao"]
