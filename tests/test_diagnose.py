"""The diagnosis engine, driven entirely by recorded responses.

No test here reaches a model. The suite-wide hermetic fixture in
``conftest.py`` blocks outbound sockets and nothing in this file carries the
``allow_network`` escape hatch, so a live call would fail the run rather than
quietly succeed and bill someone.
"""

from __future__ import annotations

import importlib.util
import sys

import pytest
from recordings import RaisingClient, RecordedClient, load_bundle

from deadman.diagnose.engine import DiagnosisEngine
from deadman.diagnose.prompt import (
    PROMPT_VERSION,
    RESPONSE_CONTRACT,
    prompt_fingerprint,
    render_prompt,
)
from deadman.diagnose.schema import DiagnosisStatus, evidence_id

DISK = "host:mac/disk#7f8f3eb7"
METRICOOL = "metricool:fwtx_dao#ace64ba3"


def engine_for(name: str) -> tuple[DiagnosisEngine, RecordedClient]:
    client = RecordedClient(name)
    return DiagnosisEngine(client=client), client


# --- the recordings themselves are still valid ---------------------------


def test_recorded_evidence_ids_match_the_derived_scheme():
    """If the id derivation drifts, the recordings must fail loudly rather
    than quietly citing evidence that no longer resolves."""
    ids = {evidence_id(e) for e in load_bundle("bundle-disk-cascade")}
    assert {DISK, METRICOOL} <= ids


# --- the happy path ------------------------------------------------------


def test_a_grounded_response_yields_a_grounded_diagnosis():
    engine, client = engine_for("grounded-disk-cascade")
    d = engine.diagnose(client.bundle)

    assert d.status is DiagnosisStatus.GROUNDED
    assert d.is_actionable
    assert "upload worker" in d.hypothesis.lower()
    assert not d.rejected_claims


def test_a_markdown_fenced_response_is_read_not_rejected():
    """Models wrap JSON in fences constantly. Treating that as a contract
    violation would throw away good diagnoses over formatting."""
    engine, client = engine_for("grounded-disk-cascade")
    assert engine.diagnose(client.bundle).status is DiagnosisStatus.GROUNDED


def test_the_diagnosis_rests_on_the_evidence_ids_it_cited():
    engine, client = engine_for("grounded-disk-cascade")
    d = engine.diagnose(client.bundle)

    assert set(d.evidence_ids) == {DISK, METRICOOL}
    assert len(d.evidence_ids) == len(set(d.evidence_ids)), "ids must be deduplicated"


def test_the_blind_surface_is_not_claimed_as_support():
    """The bundle contains an unobservable SMS relay. The model did not cite
    it, so it must not appear among the evidence the diagnosis rests on."""
    engine, client = engine_for("grounded-disk-cascade")
    assert not any(i.startswith("sms:relay") for i in engine.diagnose(client.bundle).evidence_ids)


def test_unstructured_detail_is_what_the_diagnosis_is_built_from():
    """`Evidence.detail` is free-form raw failure material — status codes,
    worker log lines, slopes. Reading it is the entire job of this layer, so a
    citation has to be able to land inside it."""
    engine, client = engine_for("grounded-disk-cascade")
    quotes = [c.quote for c in engine.diagnose(client.bundle).citations]

    assert "upload worker: OSError [Errno 28] no space left on device" in quotes
    assert "slope_gb_per_day=-20.0" in quotes


# --- provenance ----------------------------------------------------------


def test_model_temperature_and_prompt_version_are_recorded():
    engine, client = engine_for("grounded-disk-cascade")
    d = engine.diagnose(client.bundle)

    assert d.model == "gemini-3.5-flash"
    assert d.temperature == 0.0
    assert d.prompt_version == PROMPT_VERSION


@pytest.mark.parametrize(
    "recording",
    ["grounded-disk-cascade", "fabricated-token-claim", "prose-not-json", "no-citations"],
)
def test_provenance_rides_on_rejected_and_unavailable_diagnoses_too(recording: str):
    """A hypothesis without the model, temperature and prompt version that
    produced it is not reproducible, and that is as true of the ones thrown
    out as of the ones kept."""
    engine, client = engine_for(recording)
    d = engine.diagnose(client.bundle)

    assert d.model and d.prompt_version
    assert d.temperature == 0.0


def test_provenance_survives_the_model_being_unreachable():
    engine = DiagnosisEngine(client=RaisingClient())
    d = engine.diagnose(load_bundle("bundle-disk-cascade"))

    assert d.status is DiagnosisStatus.UNAVAILABLE
    assert d.model == "gemini-3.5-flash"
    assert d.prompt_version == PROMPT_VERSION


# --- rejection: the model may not assert what it was not given -----------


def test_a_fabricated_claim_is_rejected():
    """The planted fabrication. Nothing in the evidence mentions a token, so
    the model does not get to say one expired — even though the rest of its
    answer cites correctly."""
    engine, client = engine_for("fabricated-token-claim")
    d = engine.diagnose(client.bundle)

    assert d.status is DiagnosisStatus.UNGROUNDED
    assert not d.is_actionable
    assert d.confidence == 0.0
    assert any("oauth token expired" in r.lower() for r in d.rejected_claims)


def test_one_fabrication_discards_the_whole_answer():
    """Not "drop the bad citation and keep the rest". The hypothesis was
    reasoned from the invented fact, so salvaging the surviving citations
    would leave a conclusion standing on a premise that was thrown out."""
    engine, client = engine_for("fabricated-token-claim")
    d = engine.diagnose(client.bundle)

    assert d.evidence_ids == ()
    assert d.citations == ()


def test_a_rejected_hypothesis_is_still_shown_to_the_human():
    """Rejected is not deleted. An operator needs to see what the model tried
    to conclude, or the rejection is unreviewable."""
    engine, client = engine_for("fabricated-token-claim")
    assert "oauth token" in engine.diagnose(client.bundle).hypothesis.lower()


def test_a_hallucinated_surface_is_rejected():
    engine, client = engine_for("hallucinated-surface")
    d = engine.diagnose(client.bundle)

    assert d.status is DiagnosisStatus.UNGROUNDED
    assert any("instagram" in r for r in d.rejected_claims)


def test_a_hypothesis_with_no_citations_is_rejected():
    """Confidence 0.9 and nothing under it. This is the shape of the answer
    this whole layer exists to refuse."""
    engine, client = engine_for("no-citations")
    d = engine.diagnose(client.bundle)

    assert d.status is DiagnosisStatus.UNGROUNDED
    assert any("no cited evidence" in r for r in d.rejected_claims)


def test_an_evidence_id_smuggled_into_the_prose_is_rejected():
    """Every citation in this response is legitimate; the invented fact rides
    in the hypothesis text instead, attributed to evidence that was never
    supplied. Checking only the citations array would pass it."""
    engine, client = engine_for("smuggled-id-in-hypothesis")
    d = engine.diagnose(client.bundle)

    assert d.status is DiagnosisStatus.UNGROUNDED
    assert any("gmail:alerts#5c5c5c5c" in r for r in d.rejected_claims)


def test_confidence_outside_the_contract_is_rejected():
    engine, client = engine_for("confidence-out-of-range")
    d = engine.diagnose(client.bundle)

    assert d.status is DiagnosisStatus.UNGROUNDED
    assert d.confidence == 0.0


# --- unavailable is not a verdict ----------------------------------------


def test_an_unreadable_response_is_unavailable_not_ungrounded():
    """These mean different things. Ungrounded says the model asserted
    something false; unavailable says we could not read what it asserted. A
    report that conflates them tells an operator to distrust a model that may
    have been fine."""
    engine, client = engine_for("prose-not-json")
    d = engine.diagnose(client.bundle)

    assert d.status is DiagnosisStatus.UNAVAILABLE
    assert not d.is_actionable


def test_the_engine_never_raises_when_the_model_does():
    engine = DiagnosisEngine(client=RaisingClient())
    d = engine.diagnose(load_bundle("bundle-disk-cascade"))

    assert d.status is DiagnosisStatus.UNAVAILABLE
    assert "ConnectionError" in str(d.detail)


def test_an_empty_bundle_never_reaches_the_model():
    """With nothing to reason over, anything the model says is invention. Do
    not pay for the call and do not create the opportunity."""

    class Tripwire:
        model = "gemini-3.5-flash"
        temperature = 0.0

        def complete(self, prompt: str) -> str:  # pragma: no cover - must not run
            raise AssertionError("the model was consulted with no evidence")

    d = DiagnosisEngine(client=Tripwire()).diagnose([])
    assert d.status is DiagnosisStatus.UNAVAILABLE


# --- confidence is capped, not accepted ----------------------------------


def test_confidence_is_capped_by_the_weakest_cited_evidence():
    """The model claimed 0.7 while leaning on a scheduler report. The
    scheduler saying so is the weakest tier there is, and it sets the
    ceiling regardless of how the disk read was obtained."""
    engine, client = engine_for("grounded-disk-cascade")
    d = engine.diagnose(client.bundle)

    assert d.claimed_confidence == 0.7
    assert d.confidence < d.claimed_confidence
    assert d.confidence <= 0.4


def test_the_cap_does_not_bind_when_the_evidence_can_carry_the_claim():
    """Capping must not be a blanket haircut, or it stops carrying meaning."""
    engine, client = engine_for("grounded-disk-only")
    d = engine.diagnose(client.bundle)

    assert d.confidence == d.claimed_confidence == 0.7


# --- the prompt ----------------------------------------------------------


def test_the_prompt_shows_the_model_the_ids_it_must_cite():
    bundle = load_bundle("bundle-disk-cascade")
    rendered = render_prompt(bundle)

    for e in bundle:
        assert evidence_id(e) in rendered


def test_the_prompt_shows_the_unstructured_detail():
    rendered = render_prompt(load_bundle("bundle-disk-cascade"))
    assert "OSError [Errno 28] no space left on device" in rendered


def test_the_prompt_states_the_no_invention_rule():
    rendered = render_prompt(load_bundle("bundle-disk-cascade"))
    assert "verbatim" in rendered.lower()
    assert RESPONSE_CONTRACT in rendered


def test_the_prompt_explains_that_unobservable_is_not_healthy():
    """The bundle's SMS relay is a blind spot. A model told only "no result"
    will reason as though the surface is fine, which is the original sin this
    whole codebase is written against."""
    rendered = render_prompt(load_bundle("bundle-disk-cascade")).lower()
    assert "unobservable" in rendered
    assert "blind, not healthy" in rendered


def test_editing_the_prompt_without_bumping_its_version_fails_this_test():
    """The version is only worth recording if it actually tracks the prompt.
    Change the wording, change the constant below and `PROMPT_VERSION` with
    it, so a diagnosis produced last week can still be explained."""
    assert PROMPT_VERSION == "diagnose/v1"
    assert prompt_fingerprint() == "f91dc1a615b1c84a"


# --- offline by construction ---------------------------------------------


def test_the_engine_pulls_in_no_model_sdk():
    """Importing the diagnosis layer must not drag in a model SDK. If it did,
    the offline guarantee would rest on nobody having installed one, and the
    day someone did the tests would start reaching Vertex."""
    leaked = [m for m in sys.modules if m.startswith(("google.adk", "google.genai"))]
    assert not leaked, f"{leaked} imported by the diagnosis layer"


def test_the_gemini_adapter_imports_without_the_sdk_present():
    """The adapter has to be importable everywhere the package is, or every
    consumer ends up guarding its imports. The SDK is reached for inside the
    constructor, not at module scope."""
    from deadman.diagnose import gemini

    assert hasattr(gemini.GeminiClient, "complete")


def test_constructing_the_gemini_client_without_the_sdk_says_so_plainly():
    """Fail at startup, not at 3am mid-incident. A monitor that discovers its
    brain is missing while diagnosing an outage has become part of it."""
    from deadman.diagnose.gemini import GeminiClient, ModelSdkMissing

    try:
        installed = importlib.util.find_spec("google.adk") is not None
    except ModuleNotFoundError:  # the `google` namespace package is absent entirely
        installed = False
    if installed:  # pragma: no cover - depends on the environment, not the code
        pytest.skip("google-adk is installed; the missing-SDK path cannot be exercised")

    with pytest.raises(ModelSdkMissing) as caught:
        GeminiClient()

    assert "google-adk" in str(caught.value)
    assert "deadman[gemini]" in str(caught.value)


def test_diagnosis_defaults_to_a_deterministic_temperature():
    """Provenance is the point of recording temperature. A diagnosis produced
    at temperature 0.9 cannot be re-derived from the record of it, so the
    default has to be the reproducible one."""
    from deadman.diagnose.gemini import DEFAULT_MODEL, DEFAULT_TEMPERATURE

    assert DEFAULT_TEMPERATURE == 0.0
    assert DEFAULT_MODEL.startswith("gemini-")


def test_no_diagnosis_test_opts_out_of_the_hermetic_fixture(request: pytest.FixtureRequest):
    """`allow_network` is the one escape hatch from the socket block. It has
    no business in this file: every response these tests need is on disk."""
    offenders = [
        item.nodeid
        for item in request.session.items
        if "test_diagnose" in item.nodeid and item.get_closest_marker("allow_network")
    ]
    assert not offenders
