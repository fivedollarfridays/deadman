"""The committed real-world capture is what it claims to be.

Not a parser test — ``deadman.probes.morning_brief`` is already covered by
``tests/test_morning_brief_probe.py`` against synthetic logs. This locks the
one property that makes ``tests/fixtures/real-morning-brief-fault.json``
worth committing at all: it is a real ``FAULT``, not an authored placeholder
that happens to look like one. See ``tests/fixtures/README.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "real-morning-brief-fault.json"


def test_the_captured_fixture_is_marked_as_real_and_current():
    payload = json.loads(FIXTURE.read_text())

    assert payload["captured"] is True
    assert payload["evidence"]["surface"] == "cron:morning-brief"


def test_the_captured_fixture_is_a_real_fault_not_a_healthy_placeholder():
    """The whole reason this fixture exists: the acceptance test for DM2.5 is
    not synthetic. A committed 'HEALTHY' row here would mean the capture
    happened after someone fixed morning_brief_send.py, at which point this
    fixture stops being evidence of anything and must be recaptured or
    retired, not quietly reused."""
    payload = json.loads(FIXTURE.read_text())
    evidence = payload["evidence"]

    assert evidence["observation"] == "fault"
    assert evidence["method"] == "local_artifact"
    assert evidence["detail"]["age_hours"] > evidence["detail"]["window_hours"]
