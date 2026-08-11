"""The disk-fills-then-everything-dies case, and the ways it must not fire.

Every incident here comes out of the real :class:`DiagnosisEngine` replaying a
recorded response over ``bundle-disk-cascade`` — one host, three surfaces, no
lineage graph between any of them. What is under test is the actual seam
between correlation and diagnosis rather than a hand-built object with the
right fields on it.
"""

from __future__ import annotations

from recordings import RaisingClient, RecordedClient, load_bundle

from deadman.correlate.engine import Correlator
from deadman.correlate.incident import Basis, CorrelationStatus
from deadman.diagnose.engine import DiagnosisEngine
from deadman.diagnose.schema import DiagnosisStatus

CASCADE = "bundle-disk-cascade"

#: Guards the tests that assert a *grounded* answer still failed to correlate.
#: An ungrounded answer produces ``UNCORRELATED`` too, so if the evidence-id
#: scheme ever drifts out from under these recordings they would keep passing
#: for entirely the wrong reason — proving only that a broken citation is
#: rejected, which is another layer's test.
GROUNDED_OR_VACUOUS = "fixture must be grounded, or this asserts nothing about correlation"


def correlate(recording: str, evidence=None):
    client = RecordedClient(recording)
    correlator = Correlator(diagnosis=DiagnosisEngine(client=client))
    return correlator.correlate(load_bundle(CASCADE) if evidence is None else evidence), client


# --- the cascade ----------------------------------------------------------


def test_concurrent_faults_are_offered_as_one_incident():
    """AC: concurrent faults across surfaces are offered as one incident with a
    hypothesised shared cause. The disk and the scheduler have nothing
    declaring them related — one is ``shutil.disk_usage`` on a laptop, the
    other a SaaS API — and they come back as a single incident anyway."""
    incidents, _ = correlate("grounded-disk-cascade")

    assert len(incidents) == 1
    assert incidents[0].status is CorrelationStatus.CORRELATED
    assert incidents[0].surfaces == ("host:mac/disk", "metricool:fwtx_dao")
    assert "ENOSPC" in incidents[0].shared_cause
    assert "upstream of the Metricool failure" in incidents[0].shared_cause


def test_the_relationship_is_inferred_never_traversed():
    """AC: the report states the relationship was inferred, not traversed. The
    basis is a carried field rather than a turn of phrase in the prose."""
    incidents, _ = correlate("grounded-disk-cascade")

    assert incidents[0].basis is Basis.INFERRED


def test_correlation_confidence_is_carried_and_capped():
    """AC: correlation confidence is carried and surfaced, never implied.

    The model asked for 0.7. It tied the disk to the scheduler by citing the
    scheduler, and the scheduler is ``Method.REPORTED`` — a heartbeat wearing a
    hat — so the most this correlation can be held at is 0.4. Both numbers ride
    on the incident, because the gap between them is itself worth reading.
    """
    incidents, _ = correlate("grounded-disk-cascade")

    assert incidents[0].confidence == 0.4
    assert incidents[0].claimed_confidence == 0.7


def test_the_surface_the_correlation_did_not_explain_is_named():
    """The relay was blind through all of this. It is not a member, it is not
    excluded, and it is emphatically not fine — so it is listed. A correlation
    that quietly dropped it would be the "4 healthy" lie one layer up."""
    incidents, _ = correlate("grounded-disk-cascade")

    assert incidents[0].unexplained == ("sms:relay",)
    assert "sms:relay" not in incidents[0].surfaces


def test_the_incident_carries_the_diagnosis_that_produced_it():
    """Provenance, same as everywhere else here: model, temperature and prompt
    version, or the hypothesis is not reproducible and not evidence."""
    incidents, client = correlate("grounded-disk-cascade")

    assert incidents[0].diagnosis.model == client.model
    assert incidents[0].diagnosis.prompt_version == "diagnose/v1"
    assert incidents[0].evidence_ids == incidents[0].diagnosis.evidence_ids


# --- co-occurrence alone is never enough ----------------------------------


def test_a_grounded_hypothesis_reaching_one_surface_is_not_a_correlation():
    """The near-miss, and the reason this task is not just a time-bucket.

    ``grounded-disk-only`` is a perfectly good diagnosis over the same three
    co-occurring rows — it is just a diagnosis *about the disk*. Three broken
    things were in the window and the evidence tied one of them, so there is no
    relationship, however strongly the timing suggests one.
    """
    incidents, _ = correlate("grounded-disk-only")

    assert incidents[0].diagnosis.status is DiagnosisStatus.GROUNDED, GROUNDED_OR_VACUOUS
    assert incidents[0].status is CorrelationStatus.UNCORRELATED
    assert incidents[0].surfaces == ()
    assert incidents[0].confidence == 0.0
    assert "host:mac/disk" in incidents[0].reason


def test_a_surface_we_could_not_see_is_never_the_second_leg():
    """The same rule as candidacy, enforced again at the outcome — because the
    model gets to choose what it cites, and it may choose a blind row.

    ``grounded-blind-relay-tie`` is fully grounded: it quotes the disk trend and
    it quotes the relay's own "cannot observe". Two surfaces, two citations, one
    tidy story — and still no correlation, because one of those surfaces is a
    record of our blindness rather than a fault. A relay we could not reach
    cannot corroborate anything, and a correlation drawn to it would be
    reasoning from an absence of evidence.
    """
    incidents, _ = correlate("grounded-blind-relay-tie")

    assert incidents[0].diagnosis.status is DiagnosisStatus.GROUNDED, GROUNDED_OR_VACUOUS
    assert incidents[0].status is CorrelationStatus.UNCORRELATED
    assert incidents[0].surfaces == ()
    assert "host:mac/disk" in incidents[0].reason


def test_a_cited_blind_row_is_accounted_for_even_though_it_is_not_a_member():
    """It was looked at and written about, which is the opposite of dropped.
    The surface nobody mentioned is the one that needs the callout."""
    incidents, _ = correlate("grounded-blind-relay-tie")

    assert "sms:relay" not in incidents[0].surfaces
    assert "sms:relay" in incidents[0].diagnosis.evidence_ids[1]


def test_a_rejected_hypothesis_does_not_become_a_relationship():
    """``fabricated-token-claim`` invents a fact among true ones. The whole
    answer is discarded one layer down, and nothing here launders the leftovers
    into a correlation."""
    incidents, _ = correlate("fabricated-token-claim")

    assert incidents[0].status is CorrelationStatus.UNCORRELATED
    assert incidents[0].diagnosis.rejected_claims
    assert "rejected" in incidents[0].reason


def test_a_silent_model_leaves_the_relationship_unknown_not_absent():
    """The distinction that must never collapse. A model we could not reach
    tells us nothing about whether these faults share a cause — and an operator
    reading "uncorrelated" would conclude, wrongly, that we checked."""
    correlator = Correlator(diagnosis=DiagnosisEngine(client=RaisingClient()))
    incidents = correlator.correlate(load_bundle(CASCADE))

    assert incidents[0].status is CorrelationStatus.UNAVAILABLE
    assert incidents[0].status is not CorrelationStatus.UNCORRELATED
    assert "unknown" in incidents[0].reason


def test_an_unestablished_incident_still_reports_every_surface():
    """No relationship is not no finding. These surfaces did fail together, and
    a correlator that returned nothing would erase that."""
    incidents, _ = correlate("grounded-disk-only")

    assert incidents[0].candidate_surfaces == (
        "host:mac/disk",
        "metricool:fwtx_dao",
        "sms:relay",
    )
    assert incidents[0].unexplained == incidents[0].candidate_surfaces


def test_an_isolated_fault_never_reaches_the_model_at_all():
    """AC: a single isolated fault never produces a correlation — enforced by
    absence. No candidate means no prompt is rendered and no model is called,
    which is the only form of enforcement that cannot be argued around by a
    later change to how an answer is interpreted."""
    client = RecordedClient("grounded-disk-cascade")
    lone = [e for e in load_bundle(CASCADE) if e.surface == "host:mac/disk"]

    incidents = Correlator(diagnosis=DiagnosisEngine(client=client)).correlate(lone)

    assert incidents == []
    assert client.prompts == []


def test_nothing_here_can_produce_a_traversed_basis():
    """``Basis.TRAVERSED`` exists so a stored incident can say which kind of
    claim it is. Nothing in this repo may emit one: there is no lineage graph
    across these surfaces to walk."""
    for recording in ("grounded-disk-cascade", "grounded-disk-only", "hallucinated-surface"):
        incidents, _ = correlate(recording)
        assert [i.basis for i in incidents] == [Basis.INFERRED]
