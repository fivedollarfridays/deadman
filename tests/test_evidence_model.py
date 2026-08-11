"""Locks the evidence model contract.

Two claims this suite exists to guard: absence is a distinct state from
failure (see ``Observation.UNOBSERVABLE``), and evidence carries how it was
obtained (see ``Method`` trust ordering and ``provenance_row``).
"""

from __future__ import annotations

from datetime import datetime

from deadman.evidence.model import (
    Evidence,
    Method,
    Observation,
    trust,
    unobservable,
)


def test_destination_api_outranks_reported() -> None:
    assert trust(Method.DESTINATION_API) > trust(Method.REPORTED)


def test_provenance_row_returns_source_method_surface_and_iso_timestamp() -> None:
    evidence = Evidence(
        surface="host:disk/",
        observation=Observation.HEALTHY,
        method=Method.LOCAL_ARTIFACT,
        summary="12.0GB free, 90 days of runway",
        source="statvfs:/",
    )

    source, method, surface, read_at = evidence.provenance_row()

    assert source == "statvfs:/"
    assert method == Method.LOCAL_ARTIFACT.value
    assert surface == "host:disk/"
    assert datetime.fromisoformat(read_at) == evidence.read_at


def test_unobservable_records_the_reason_in_detail() -> None:
    evidence = unobservable(
        "host:disk/", "statvfs:/", "cannot stat volume: permission denied"
    )

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.detail["reason"] == "cannot stat volume: permission denied"


def test_unobservable_merges_extra_detail_alongside_the_reason() -> None:
    evidence = unobservable("host:disk/", "statvfs:/", "boom", errno=13)

    assert evidence.detail == {"reason": "boom", "errno": 13}
