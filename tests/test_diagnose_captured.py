"""Replay a response a real model actually produced.

Every other recording in ``tests/recorded/`` was authored against the response
contract in :mod:`deadman.diagnose.prompt`. Those prove the parser handles a
shape we invented, which is worth something but is not the same claim. This
one was captured from live ``gemini-3.5-flash`` (see
``docs/gemini-verification.md``), so it proves the contract survives contact
with the thing it was written for.

Kept separate from ``test_diagnose.py`` deliberately. When these two disagree,
the authored fixture is the one that is wrong.
"""

from __future__ import annotations

import json

from recordings import RECORDED, RecordedClient

from deadman.correlate.engine import Correlator
from deadman.diagnose.engine import DiagnosisEngine
from deadman.diagnose.schema import DiagnosisStatus, evidence_id

CAPTURE = "captured-disk-cascade"


def test_the_recording_is_actually_a_capture():
    # Guards the honesty of the claim this whole file rests on. If someone
    # hand-edits this fixture, it stops being evidence about a real model.
    envelope = json.loads((RECORDED / f"{CAPTURE}.json").read_text())

    assert envelope["captured"] is True
    assert envelope["model"] == "gemini-3.5-flash"
    assert envelope["captured_at"]


def test_a_real_model_response_grounds():
    client = RecordedClient(CAPTURE)

    diagnosis = DiagnosisEngine(client=client).diagnose(client.bundle)

    assert diagnosis.status is DiagnosisStatus.GROUNDED
    assert diagnosis.hypothesis


def test_the_real_response_cites_evidence_that_resolves():
    # The failure mode this catches is a model citing an id that looks right
    # and does not exist. Authored fixtures can never surprise us here,
    # because we wrote the ids into them.
    client = RecordedClient(CAPTURE)
    bundle = client.bundle
    known = {evidence_id(e) for e in bundle}

    diagnosis = DiagnosisEngine(client=client).diagnose(bundle)

    assert diagnosis.evidence_ids
    assert set(diagnosis.evidence_ids) <= known


def test_the_real_response_names_disk_exhaustion_as_upstream():
    # The cascade is the case correlation exists for: the volume filling is
    # upstream of the publish failure, not beside it. A real model reaching
    # that conclusion from evidence alone, with no lineage graph available,
    # is the substantive claim this project makes.
    client = RecordedClient(CAPTURE)

    diagnosis = DiagnosisEngine(client=client).diagnose(client.bundle)

    assert "space" in diagnosis.hypothesis.lower()
    assert len(diagnosis.evidence_ids) >= 2


def test_the_captured_diagnosis_correlates_into_one_incident():
    client = RecordedClient(CAPTURE)
    bundle = client.bundle

    incidents = Correlator(diagnosis=DiagnosisEngine(client=client)).correlate(bundle)

    assert len(incidents) == 1
    assert len(incidents[0].surfaces) >= 2
