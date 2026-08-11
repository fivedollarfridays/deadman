"""The entry point a scheduler actually calls, and what it does when dead.

Exit codes are the interface here. A cron line, a Cloud Scheduler job or a
systemd timer reads nothing but the status, so a self-check that prints a
worried paragraph and exits 0 has reported nothing at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from deadman.remediate.alert import AlertChannel, AlertChannelInvalid
from deadman.self_check import SelfEvidenceLog, main, run_self_check

MONITORED = ("cron:morning-brief", "sms:relay")


def _log_aged(tmp_path, hours: float) -> SelfEvidenceLog:
    log = SelfEvidenceLog(path=tmp_path / "self.jsonl")
    log.record(
        sweep_size=2,
        blind=0,
        when=datetime.now(timezone.utc) - timedelta(hours=hours),
    )
    return log


def _channel():
    sent: list[str] = []
    return sent, AlertChannel(
        transport="email:ops@example.com", send=sent.append, monitored=MONITORED
    )


def test_main_exits_zero_when_live(tmp_path, monkeypatch, capsys):
    _log_aged(tmp_path, 1)
    monkeypatch.setenv("DEADMAN_SELF_LOG", str(tmp_path / "self.jsonl"))

    assert main([]) == 0


def test_main_exits_non_zero_when_stale(tmp_path, monkeypatch, capsys):
    _log_aged(tmp_path, 100)
    monkeypatch.setenv("DEADMAN_SELF_LOG", str(tmp_path / "self.jsonl"))

    assert main([]) != 0


def test_main_exits_non_zero_when_there_is_no_evidence(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DEADMAN_SELF_LOG", str(tmp_path / "absent.jsonl"))

    assert main([]) != 0


def test_a_dead_check_raises_the_alarm_out_of_band(tmp_path):
    sent, channel = _channel()
    log = _log_aged(tmp_path, 100)

    result = run_self_check(log, window_hours=30, channel=channel)

    assert result.exit_code != 0
    assert len(sent) == 1
    assert "sweep" in sent[0]


def test_a_live_check_stays_quiet(tmp_path):
    sent, channel = _channel()
    log = _log_aged(tmp_path, 1)

    run_self_check(log, window_hours=30, channel=channel)

    assert sent == []


def test_the_alarm_cannot_be_wired_through_a_watched_surface():
    # The constraint that makes the alert worth having, asserted where it is
    # cheap to fix rather than during the outage it exists for.
    with pytest.raises(AlertChannelInvalid):
        AlertChannel(transport="cron:morning-brief", send=print, monitored=MONITORED)
