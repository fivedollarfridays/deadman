"""A fault that heals and comes back inside the throttle window alarms again.

Audit finding D2: ``evaluate`` never sent healthy rows, so the throttle never
learned about a recovery. Fault at t0 alarmed; the surface healed silently;
the same fault at t0 + 40 minutes had the same key and state inside the
one-hour window and was suppressed as a "repeat". ``test_transports.py`` pins
"never suppress a state change" on the throttle alone, which is why the suite
was green on a property the integrated path lacked.

Every test here drives the scheduled endpoint, with the real throttled email
channel built by ``alarm_from_env``, on a clock the test moves by hand.
"""

from __future__ import annotations

import pytest
from alarm_harness import AUTHORIZED, Clock, StaticProbe, install_fake_smtp, production_endpoint

from deadman.evidence.model import Observation

SURFACE = "host:disk/"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_fake_smtp(monkeypatch)


def _sweep(endpoint, clock: Clock, probe: StaticProbe, observation: Observation, minutes: float):
    probe.observation = observation
    clock.advance(minutes)
    status, _ = endpoint.handle(dict(AUTHORIZED))
    assert status.startswith("200")


def test_a_refault_after_a_heal_inside_the_window_alarms_again(outbox):
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)
    endpoint = production_endpoint([probe], clock=clock)

    _sweep(endpoint, clock, probe, Observation.FAULT, 0)
    _sweep(endpoint, clock, probe, Observation.HEALTHY, 15)
    _sweep(endpoint, clock, probe, Observation.FAULT, 25)

    faults = [m for m in outbox if f"{SURFACE} is fault" in m]
    assert len(faults) == 2, outbox


def test_a_heal_after_an_alerted_fault_sends_one_recovery_notice(outbox):
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)
    endpoint = production_endpoint([probe], clock=clock)

    _sweep(endpoint, clock, probe, Observation.FAULT, 0)
    _sweep(endpoint, clock, probe, Observation.HEALTHY, 15)
    _sweep(endpoint, clock, probe, Observation.HEALTHY, 15)

    recoveries = [m for m in outbox if "recovered" in m]
    assert len(recoveries) == 1, outbox
    assert SURFACE in recoveries[0]


def test_a_surface_that_never_alarmed_sends_no_recovery(outbox):
    """Otherwise every healthy surface would mail on every cold start."""
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.HEALTHY)
    endpoint = production_endpoint([probe], clock=clock)

    _sweep(endpoint, clock, probe, Observation.HEALTHY, 0)
    _sweep(endpoint, clock, probe, Observation.HEALTHY, 15)

    assert outbox == []


def test_a_persisting_fault_inside_the_window_is_still_throttled(outbox):
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)
    endpoint = production_endpoint([probe], clock=clock)

    for minutes in (0, 15, 15, 15):
        _sweep(endpoint, clock, probe, Observation.FAULT, minutes)

    assert len(outbox) == 1, outbox
