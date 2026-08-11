"""Candidacy: which faults are even worth asking about.

This is the deterministic half of correlation and it deliberately establishes
almost nothing. Two probes in one sweep carry near-identical ``read_at`` values
whether or not their faults share a cause, so co-occurrence in read time is a
filter, not evidence. What it buys is the right to ask the question at all —
and, just as importantly, the duty not to ask it when there is nothing to ask
about.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from deadman.correlate.window import DEFAULT_WINDOW_SECONDS, candidates
from deadman.evidence.model import Evidence, Method, Observation

T0 = datetime(2026, 8, 11, 3, 0, 0, tzinfo=timezone.utc)


def fault(surface: str, offset_seconds: float = 0.0, **detail) -> Evidence:
    return Evidence(
        surface=surface,
        observation=Observation.FAULT,
        method=Method.LOCAL_ARTIFACT,
        summary=f"{surface} is broken",
        source=f"probe:{surface}",
        read_at=T0 + timedelta(seconds=offset_seconds),
        detail=detail,
    )


def blind(surface: str, offset_seconds: float = 0.0) -> Evidence:
    return Evidence(
        surface=surface,
        observation=Observation.UNOBSERVABLE,
        method=Method.REPORTED,
        summary=f"cannot observe {surface}",
        source=f"probe:{surface}",
        read_at=T0 + timedelta(seconds=offset_seconds),
    )


def healthy(surface: str, offset_seconds: float = 0.0) -> Evidence:
    return Evidence(
        surface=surface,
        observation=Observation.HEALTHY,
        method=Method.DESTINATION_API,
        summary=f"{surface} is fine",
        source=f"probe:{surface}",
        read_at=T0 + timedelta(seconds=offset_seconds),
    )


# --- a candidate needs two faulting surfaces, and nothing else counts ------


def test_concurrent_faults_on_two_surfaces_are_one_candidate():
    found = candidates([fault("host:mac/disk"), fault("metricool:fwtx_dao", 4)])

    assert len(found) == 1
    assert found[0].span == ("host:mac/disk", "metricool:fwtx_dao")


def test_a_single_isolated_fault_is_never_a_candidate():
    """AC: a single isolated fault never produces a correlation. Enforced here,
    at the cheapest possible point, so the model is never even asked."""
    assert candidates([fault("host:mac/disk"), healthy("metricool:fwtx_dao", 3)]) == []


def test_two_faults_on_the_same_surface_are_not_cross_surface():
    """One surface failing twice is one surface failing twice. Correlation is a
    claim about a relationship *between* surfaces."""
    assert candidates([fault("host:mac/disk"), fault("host:mac/disk", 5)]) == []


def test_blindness_is_never_the_second_leg_of_a_correlation():
    """A surface we could not see cannot corroborate anything. Inferring a
    shared cause from an absence of evidence is the substitution this whole
    project exists to prevent — so a lone fault beside a blind spot stays a
    lone fault."""
    assert candidates([fault("host:mac/disk"), blind("sms:relay", 2)]) == []


def test_faults_further_apart_than_the_window_do_not_co_occur():
    apart = DEFAULT_WINDOW_SECONDS + 60
    assert candidates([fault("host:mac/disk"), fault("metricool:fwtx_dao", apart)]) == []


# --- what a candidate carries ---------------------------------------------


def test_blind_rows_in_the_window_ride_along_as_context():
    """Not as a leg, but not dropped either. The model is shown them (it is
    instructed that blind is not healthy) and the report has to account for
    them, which it cannot do if candidacy threw them away."""
    found = candidates(
        [fault("host:mac/disk"), fault("metricool:fwtx_dao", 4), blind("sms:relay", 6)]
    )

    assert [e.surface for e in found[0].context] == ["sms:relay"]
    assert found[0].span == ("host:mac/disk", "metricool:fwtx_dao")


def test_healthy_rows_are_not_carried():
    found = candidates(
        [fault("host:mac/disk"), fault("metricool:fwtx_dao", 4), healthy("cron:brief", 5)]
    )

    assert found[0].context == ()
    assert "cron:brief" not in found[0].span


def test_evidence_is_everything_the_candidate_covers():
    """``evidence`` is what gets handed to the model: legs and context both."""
    found = candidates(
        [fault("host:mac/disk"), fault("metricool:fwtx_dao", 4), blind("sms:relay", 6)]
    )

    assert len(found[0].evidence) == 3
    assert found[0].evidence[:2] == found[0].faults


def test_candidacy_does_not_depend_on_input_order():
    rows = [fault("metricool:fwtx_dao", 4), blind("sms:relay", 6), fault("host:mac/disk")]

    assert candidates(rows) == candidates(list(reversed(rows)))


def test_two_separate_clusters_are_two_separate_candidates():
    """Far apart in time is a different incident, not a bigger one."""
    far = DEFAULT_WINDOW_SECONDS * 4
    found = candidates(
        [
            fault("host:mac/disk"),
            fault("metricool:fwtx_dao", 4),
            fault("sms:relay", far),
            fault("cron:brief", far + 3),
        ]
    )

    assert len(found) == 2
    assert found[0].span == ("host:mac/disk", "metricool:fwtx_dao")
    assert found[1].span == ("cron:brief", "sms:relay")


def test_nothing_at_all_yields_nothing():
    assert candidates([]) == []
