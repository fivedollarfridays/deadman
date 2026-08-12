"""``docs/PROOF.md`` is written from the captures, never from memory.

The case study is the project's actual argument, which makes it the document
with the most to gain from a number being rounded in the flattering direction.
A remembered "about a week" that the evidence does not support would be the
same species of dishonesty as a heartbeat: a claim nobody can check, made by
the thing making the claim.

So every duration and every timestamp in the prose has to be findable in
``tests/fixtures/real-morning-brief-fault.json`` or
``tests/fixtures/real-board-capture.json``. If the captures are ever refreshed
and the prose is not, this fails.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROOF = ROOT / "docs" / "PROOF.md"
FIXTURES = ROOT / "tests" / "fixtures"
CAPTURES = ("real-morning-brief-fault.json", "real-board-capture.json")


def _captured_text() -> str:
    return "\n".join((FIXTURES / name).read_text() for name in CAPTURES)


def test_every_duration_in_the_case_study_comes_from_a_capture():
    captured = _captured_text()

    durations = set(re.findall(r"\b\d+\.\d+h\b", PROOF.read_text()))
    assert durations, "a case study about a seven-day outage cites at least one measured age"

    unsourced = {d for d in durations if d[:-1] not in captured}
    assert not unsourced, (
        f"{sorted(unsourced)} appear in docs/PROOF.md and in neither capture. "
        f"Numbers in the case study are read out of the evidence, not recalled."
    )


def test_every_timestamp_in_the_case_study_comes_from_a_capture():
    captured = _captured_text()

    stamps = set(re.findall(r"\b2026-\d\d-\d\dT[\d:.]+", PROOF.read_text()))
    assert stamps

    unsourced = {s for s in stamps if s.rstrip(".") not in captured}
    assert not unsourced, f"{sorted(unsourced)} are not in any committed capture"


def test_the_case_study_names_both_captures_it_was_written_from():
    text = PROOF.read_text()

    for name in CAPTURES:
        assert name in text, f"a reader cannot check the claims without being told about {name}"


def test_the_case_study_states_the_detection_latency_against_the_real_delay():
    """The whole comparison: what it costs to notice now, against what it cost
    to notice by accident."""
    text = PROOF.read_text()

    assert "900s" in text, "the collector's sweep cadence is half the latency claim"
    assert "1800s" in text, "the liveness deadline is the other half: silence is not health"
    assert "30h" in text, "the probe's own tolerance is the largest term and must be stated"
    assert "seven days" in text
    assert "176.7h" in text and "185.7h" in text


def test_the_case_study_says_why_the_outage_hid_itself():
    text = PROOF.read_text().lower()

    assert "self-conceal" in text
    assert "alerting channel" in text, (
        "the reason nobody noticed is that the brief was the channel that would "
        "have announced its own death"
    )


def test_the_case_study_does_not_claim_the_board_shows_what_it_does_not():
    """The captured board came off the deployed revision, which predates
    DM2C.1's `reported_by`/`held_since`. Writing the case study around fields
    the capture does not contain is exactly the memory-over-evidence failure
    this file guards."""
    capture = (FIXTURES / "real-board-capture.json").read_text()
    text = PROOF.read_text()

    for field in ("reported_by", "held_since"):
        if field in text:
            assert field in capture or "predates" in text or "not in this capture" in text
