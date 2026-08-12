"""The demo's break-and-heal runs against a real surface, not a stub.

Every other stage of the demo is shipped code, but until now the *surface*
being broken was the one thing injected: a stub relay handed the probe a 503
through a seam. That is defensible for a carrier outage nobody can arrange on
demand, and it is still the weakest sentence in the run sheet.

``scripts/demo_real_surface`` removes it for one surface. ``MorningBriefProbe``
reads a real file on a real filesystem with no seam between it and the
evidence: the break is a real write (the outage's own last log row, taken from
``tests/fixtures/real-morning-brief-fault.json``), the heal is a real write,
and what says the surface recovered is a fresh observation of the same probe.

These tests exist to keep that property from quietly regressing into another
stub.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from demo_real_surface import (  # noqa: E402
    MONITORED,
    RealSurfaceRun,
    break_it,
    heal_it,
    outage_last_send_at,
    probe_for,
    run_segment,
    send_row,
    start_healthy,
)
from demo_stubs import ScriptedClient  # noqa: E402

from deadman.evidence.model import Method, Observation  # noqa: E402
from deadman.remediate.cause import Cause  # noqa: E402
from deadman.remediate.verify import VerificationStatus  # noqa: E402

CAPTURE = Path(__file__).resolve().parent / "fixtures" / "real-morning-brief-fault.json"


def _log(tmp_path: Path) -> Path:
    return tmp_path / "brief-send-log.jsonl"


def test_the_break_is_the_real_outages_own_last_row(tmp_path):
    """Not an invented timestamp chosen to trip the window. The row written is
    the last delivery the real brief ever made, read out of the committed
    capture."""
    captured = json.loads(CAPTURE.read_text())["evidence"]["detail"]["last_send_at"]

    log = _log(tmp_path)
    start_healthy(log)
    break_it(log)

    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["ts"] == captured == outage_last_send_at()


def test_the_break_produces_a_real_fault_read_off_the_file(tmp_path):
    log = _log(tmp_path)
    start_healthy(log)
    broken = break_it(log)

    assert broken.observation is Observation.FAULT
    # LOCAL_ARTIFACT, not REPORTED: this probe read the file itself. Nothing
    # relayed the claim, so nothing downgrades it.
    assert broken.method is Method.LOCAL_ARTIFACT
    assert broken.source == str(log)
    assert broken.detail["age_hours"] > broken.detail["window_hours"]


def test_nothing_stands_between_the_probe_and_the_evidence(tmp_path):
    """The point of the segment. The probe is constructed over a path and
    holds no client, no relay, no seam a demo could reach through."""
    log = _log(tmp_path)
    probe = probe_for(log)

    assert probe.log_path == log
    assert set(vars(probe)) == {"log_path", "window_hours"}

    segment = Path(__file__).resolve().parent.parent / "scripts" / "demo_real_surface.py"
    source = segment.read_text()
    assert "demo_stubs" not in source, "the real-surface segment must not import the demo's stubs"


def test_a_dead_cron_escalates_rather_than_acting(tmp_path):
    """There is no shipped action for a hung job on somebody's laptop, and
    inventing one is the guess the design forbids. The correct automated
    outcome is a human, reached out of band."""
    run = run_segment(_log(tmp_path), ScriptedClient())

    assert run.cause is Cause.UNKNOWN
    assert run.outcome.status is VerificationStatus.NOT_ATTEMPTED
    assert len(run.alerts) == 1
    assert "cron:morning-brief" in run.alerts[0]


def test_the_alarm_is_not_on_the_rail_that_died(tmp_path):
    """The morning brief is monitored, so an alert over the morning brief is
    the self-concealing outage this project is named after."""
    run = run_segment(_log(tmp_path), ScriptedClient())

    assert "cron:morning-brief" in MONITORED
    assert run.channel.transport.split(":", 1)[0] not in {s.split(":", 1)[0] for s in MONITORED}


def test_the_heal_is_proved_by_a_fresh_observation(tmp_path):
    log = _log(tmp_path)
    start_healthy(log)
    break_it(log)
    healed = heal_it(log)

    assert healed.observation is Observation.HEALTHY
    assert healed.source == str(log)
    # The heal is a real row appended to a real file, exactly as a repaired
    # brief job writes one — the fault row is still there underneath it.
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert len(rows) == 2


def test_the_segment_runs_end_to_end(tmp_path):
    run = run_segment(_log(tmp_path), ScriptedClient())

    assert isinstance(run, RealSurfaceRun)
    assert run.healthy.observation is Observation.HEALTHY
    assert run.broken.observation is Observation.FAULT
    assert run.healed.observation is Observation.HEALTHY
    assert run.diagnosis.evidence_ids


def test_a_row_written_now_reads_healthy_and_one_written_last_week_does_not(tmp_path):
    """The probe reads the timestamp inside the row, never the file's mtime —
    both rows here are written by this test at the same moment."""
    log = _log(tmp_path)
    send_row(log, datetime.now(timezone.utc))
    assert probe_for(log).observe().observation is Observation.HEALTHY

    log.write_text("")
    send_row(log, datetime.now(timezone.utc) - timedelta(days=7))
    assert probe_for(log).observe().observation is Observation.FAULT
