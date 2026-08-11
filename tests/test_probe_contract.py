"""Locks the probe contract's never-raise guarantee.

The failure mode this guards against: a client that swallows an error and
returns something that looks like data, so an infrastructure failure gets
laundered into a verdict about the estate. A probe that misbehaves must
degrade to ``UNOBSERVABLE``, never masquerade as evidence and never take the
rest of the sweep down with it.
"""

from __future__ import annotations

from deadman.evidence.model import Evidence, Method, Observation, unobservable
from deadman.probes.base import blind_spots, run_probe, sweep


class _RaisingProbe:
    surface = "test:raises"
    question = "does this probe raise?"

    def observe(self) -> Evidence:
        raise RuntimeError("simulated transport failure")


class _WrongReturnProbe:
    surface = "test:wrong-return"
    question = "does this probe return something other than Evidence?"

    def observe(self) -> object:
        return {"looks": "like data but is not Evidence"}


class _HealthyProbe:
    def __init__(self, surface: str) -> None:
        self._surface = surface

    @property
    def surface(self) -> str:
        return self._surface

    @property
    def question(self) -> str:
        return "is it fine?"

    def observe(self) -> Evidence:
        return Evidence(
            surface=self._surface,
            observation=Observation.HEALTHY,
            method=Method.LOCAL_ARTIFACT,
            summary="fine",
            source="test",
        )


def test_a_raising_probe_yields_unobservable_never_fault() -> None:
    evidence = run_probe(_RaisingProbe())

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.FAULT
    assert evidence.surface == "test:raises"


def test_a_probe_returning_non_evidence_is_contained_and_yields_unobservable() -> None:
    evidence = run_probe(_WrongReturnProbe())

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.surface == "test:wrong-return"


def test_a_well_behaved_probe_passes_its_evidence_through_unchanged() -> None:
    probe = _HealthyProbe("test:healthy")

    evidence = run_probe(probe)

    assert evidence.observation is Observation.HEALTHY
    assert evidence.surface == "test:healthy"


def test_sweep_isolates_a_raising_probe_from_the_rest() -> None:
    results = sweep([_RaisingProbe(), _HealthyProbe("test:healthy")])

    assert results[0].observation is Observation.UNOBSERVABLE
    assert results[1].observation is Observation.HEALTHY


def test_blind_spots_returns_unobserved_surfaces_and_excludes_healthy_ones() -> None:
    healthy = Evidence(
        surface="test:healthy",
        observation=Observation.HEALTHY,
        method=Method.LOCAL_ARTIFACT,
        summary="fine",
        source="test",
    )
    fault = Evidence(
        surface="test:fault",
        observation=Observation.FAULT,
        method=Method.LOCAL_ARTIFACT,
        summary="broken",
        source="test",
    )
    blind = unobservable("test:blind", "test", "cannot reach it")

    spots = blind_spots([healthy, fault, blind])

    assert spots == [blind]
