"""Episodes: what opens one, what restarts its schedule, what closes it.

Every sweep here is a cold start (a new endpoint and alarm over the same
store), on both backends, driven through the scheduled endpoint with the
alarm ``alarm_from_env`` builds. See ``test_alarm_backoff_schedule.py``.
"""

from __future__ import annotations

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

SURFACE = "service:staging-queue"
OTHER = "cron:devpost"
MONITORED = (SURFACE, OTHER)

FAULT, HEALTHY, BLIND = Observation.FAULT, Observation.HEALTHY, Observation.UNOBSERVABLE


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_fake_smtp(monkeypatch)


@pytest.fixture(params=sorted(STORE_FACTORIES))
def store(request: pytest.FixtureRequest):
    return STORE_FACTORIES[request.param]()


def _run(store, outbox, probes: list[StaticProbe], hours: float, script) -> list[tuple[float, str]]:
    """Sweep cold every 15 minutes; ``script(elapsed_hours)`` sets the probes."""
    clock = Clock()

    def cold() -> object:
        return production_endpoint(probes, clock=clock, monitored=MONITORED, store=store)

    return sweep_for(cold, clock, outbox, hours=hours, before_sweep=script)


def _about(sent: list[tuple[float, str]], surface: str, word: str) -> list[float]:
    return [hours for hours, body in sent if f"{surface} {word}" in body]


def test_a_state_change_inside_an_episode_alerts_at_once_and_restarts_the_schedule(outbox, store):
    """Blind from 0 h, fault from 2 h. The change is a new fact: it sends on
    that sweep, and the 6 h step is then measured from it (8 h, not 6 h)."""
    probe = StaticProbe(SURFACE, BLIND)

    def script(elapsed: float) -> None:
        probe.observation = BLIND if elapsed < 2 else FAULT

    sent = _run(store, outbox, [probe], 12, script)

    assert _about(sent, SURFACE, "is unobservable") == [0]
    assert _about(sent, SURFACE, "is fault") == [2, 8]
    assert len(sent) == 3, sent


def test_a_heal_sends_exactly_one_recovery_notice(outbox, store):
    probe = StaticProbe(SURFACE, FAULT)

    def script(elapsed: float) -> None:
        probe.observation = FAULT if elapsed < 7 else HEALTHY

    sent = _run(store, outbox, [probe], 48, script)

    assert _about(sent, SURFACE, "is fault") == [0, 6]
    assert _about(sent, SURFACE, "recovered") == [7]
    assert len(sent) == 3, sent


def test_a_heal_with_no_prior_alert_sends_nothing(outbox, store):
    """Otherwise every healthy surface would mail on every cold start."""
    sent = _run(store, outbox, [StaticProbe(SURFACE, HEALTHY)], 30, lambda elapsed: None)

    assert sent == []


def test_fault_heal_fault_sends_alert_recovery_alert_with_no_suppression(outbox, store):
    """The second fault is 30 minutes after the first: far inside the 6 h
    step, and still a new episode, because a heal closed the first one."""
    probe = StaticProbe(SURFACE, FAULT)
    states = {0: FAULT, 0.25: HEALTHY, 0.5: FAULT}

    def script(elapsed: float) -> None:
        probe.observation = states.get(elapsed, probe.observation)

    sent = _run(store, outbox, [probe], 5, script)

    assert [body.split(" — ")[0] for _, body in sent] == [
        f"deadman: {SURFACE} is fault",
        f"deadman: {SURFACE} recovered",
        f"deadman: {SURFACE} is fault",
    ]
    assert [hours for hours, _ in sent] == [0, 0.25, 0.5]


def test_two_surfaces_in_fault_keep_independent_schedules(outbox, store):
    first, second = StaticProbe(SURFACE, FAULT), StaticProbe(OTHER, HEALTHY)

    def script(elapsed: float) -> None:
        second.observation = HEALTHY if elapsed < 3 else FAULT

    sent = _run(store, outbox, [first, second], 22, script)

    assert _about(sent, SURFACE, "is fault") == [0, 6, 18]
    assert _about(sent, OTHER, "is fault") == [3, 9, 21]
    assert len(sent) == 6, sent
