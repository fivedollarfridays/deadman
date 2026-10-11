"""One persisting fault pages at 0 h, 6 h, 18 h and 42 h, on any instance.

The incident this pins: from 2026-10-09 to 2026-10-11 one ongoing fault sent
39 alert emails in about 45 hours, roughly one an hour, all unread. The repeat
throttle was an hour long and lived in instance memory, so it also forgot
itself on every Cloud Run cold start.

Every test drives the scheduled endpoint with the alarm built by
``alarm_from_env``; only the SMTP socket and the clock are replaced. The
"cold" tests build a brand new endpoint and alarm for every single sweep and
share nothing with the previous one but the store, on both backends, because
a backoff that only holds on a warm instance changes nothing the owner sees.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from alarm_harness import (
    STORE_FACTORIES,
    Clock,
    StaticProbe,
    install_fake_smtp,
    production_endpoint,
    sweep_for,
)

from deadman.evidence.model import Observation
from deadman.scheduled.backoff import BACKOFF_SCHEDULE

SURFACE = "service:staging-queue"
MONITORED = (SURFACE,)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_fake_smtp(monkeypatch)


@pytest.fixture(params=sorted(STORE_FACTORIES))
def store(request: pytest.FixtureRequest):
    return STORE_FACTORIES[request.param]()


def _hours(sent: list[tuple[float, str]]) -> list[float]:
    return [hours for hours, _ in sent]


def test_the_schedule_is_one_named_constant():
    assert BACKOFF_SCHEDULE == (
        timedelta(hours=6),
        timedelta(hours=12),
        timedelta(hours=24),
    )


def test_a_fault_held_for_48_hours_sends_four_alerts_on_a_warm_instance(outbox, store):
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)
    endpoint = production_endpoint([probe], clock=clock, monitored=MONITORED, store=store)

    sent = sweep_for(lambda: endpoint, clock, outbox, hours=48)

    assert _hours(sent) == [0, 6, 18, 42], sent


def test_a_cold_start_on_every_sweep_sends_the_same_four_alerts(outbox, store):
    """A brand new alarm with empty instance memory, 193 times running."""
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)

    def cold() -> object:
        return production_endpoint([probe], clock=clock, monitored=MONITORED, store=store)

    sent = sweep_for(cold, clock, outbox, hours=48)

    assert _hours(sent) == [0, 6, 18, 42], sent


def test_after_the_schedule_runs_out_the_repeat_is_every_24_hours(outbox, store):
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)

    def cold() -> object:
        return production_endpoint([probe], clock=clock, monitored=MONITORED, store=store)

    sent = sweep_for(cold, clock, outbox, hours=96)

    assert _hours(sent) == [0, 6, 18, 42, 66, 90], sent


def test_a_late_sweep_still_sends_the_due_repeat_exactly_once(outbox, store):
    """The 6 h mark is missed entirely (no sweep between 5 h and 7 h). The
    decision is "is a repeat due and not yet sent", so the 7 h sweep sends it,
    and the sweeps after it do not send it again."""
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)

    def cold() -> object:
        return production_endpoint([probe], clock=clock, monitored=MONITORED, store=store)

    early = sweep_for(cold, clock, outbox, hours=5)
    clock.advance(120)
    late = sweep_for(cold, clock, outbox, hours=3)

    assert _hours(early) == [0]
    assert _hours(late) == [0], late  # 0 h into the second run is 7 h in
    assert len(outbox) == 2
