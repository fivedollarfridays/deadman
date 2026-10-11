"""What a repeat tells its reader: how long, and when they will hear again."""

from __future__ import annotations

from datetime import timedelta

import pytest
from alarm_harness import T0, Clock, StaticProbe, install_fake_smtp, production_endpoint, sweep_for

from deadman.evidence.model import Observation
from deadman.scheduled.backoff import BACKOFF_SCHEDULE, SendRecord, next_repeat_at, span, stamp

SURFACE = "service:staging-queue"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_fake_smtp(monkeypatch)


def _bodies(outbox: list[str], hours: float) -> list[str]:
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)
    endpoint = production_endpoint([probe], clock=clock, monitored=(SURFACE,))
    return [body for _, body in sweep_for(lambda: endpoint, clock, outbox, hours=hours)]


def test_the_first_alert_keeps_its_line_and_says_when_the_next_repeat_is_due(outbox):
    (first,) = _bodies(outbox, 1)

    assert first.startswith(f"deadman: {SURFACE} is fault — ")
    assert "First alert for this state." in first
    assert "the next repeat is due 2026-09-27 18:00 UTC (in 6h)" in first


def test_a_repeat_states_the_held_duration_and_the_next_repeat_time(outbox):
    _, at_6h, at_18h, at_42h = _bodies(outbox, 42)

    assert "Still fault: held for 6h, first alerted 2026-09-27 12:00 UTC." in at_6h
    assert "This is repeat 1." in at_6h
    assert "the next repeat is due 2026-09-28 06:00 UTC (in 12h)" in at_6h

    assert "held for 18h" in at_18h
    assert "the next repeat is due 2026-09-29 06:00 UTC (in 1d)" in at_18h

    assert "held for 1d 18h" in at_42h
    assert "This is repeat 3." in at_42h
    assert "the next repeat is due 2026-09-30 06:00 UTC (in 1d)" in at_42h


def test_the_next_repeat_follows_the_schedule_then_holds_its_last_step():
    def after(sends: int) -> timedelta:
        return next_repeat_at(SendRecord("fault", T0, T0, sends=sends)) - T0

    assert [after(n) for n in (1, 2, 3, 4, 9)] == [
        BACKOFF_SCHEDULE[0],
        BACKOFF_SCHEDULE[1],
        BACKOFF_SCHEDULE[2],
        BACKOFF_SCHEDULE[2],
        BACKOFF_SCHEDULE[2],
    ]


def test_a_send_record_survives_its_own_round_trip():
    record = SendRecord("stale", T0, T0 + timedelta(hours=6), sends=2)

    assert SendRecord.from_document(record.to_document()) == record


@pytest.mark.parametrize(
    ("duration", "text"),
    [
        (timedelta(0), "0m"),
        (timedelta(minutes=45), "45m"),
        (timedelta(hours=6), "6h"),
        (timedelta(hours=6, minutes=15), "6h 15m"),
        (timedelta(hours=42), "1d 18h"),
        (timedelta(seconds=-5), "0m"),
    ],
)
def test_span_reads_at_a_glance(duration: timedelta, text: str):
    assert span(duration) == text


def test_stamp_is_utc_to_the_minute():
    assert stamp(T0) == "2026-09-27 12:00 UTC"
