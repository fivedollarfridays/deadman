"""What happens to a claim when it crosses a wire.

The rule under test is the reason this task exists: the service did not read
the disk, a collector says it did, and recording the collector's word as the
service's own reading would manufacture exactly the confidence this project
argues against.

The mutation these tests are built to catch is the tempting one — deleting the
mapping and passing evidence through unchanged, because "the collector already
told us the method". ``test_the_arrival_mapping_is_not_the_identity_function``
fails on precisely that edit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from deadman.evidence.model import Evidence, Method, Observation, trust
from deadman.ingest.arrival import (
    COLLECTOR_ID,
    ON_ARRIVAL,
    RECEIVED_AT,
    REPORTED_METHOD,
    WIRE_ROW_ID,
    arrival_method,
    on_arrival,
)
from deadman.store.base import row_id

READ_AT = datetime(2026, 8, 11, 6, 56, tzinfo=timezone.utc)
RECEIVED = datetime(2026, 8, 11, 7, 2, tzinfo=timezone.utc)


def _evidence(method: Method = Method.LOCAL_ARTIFACT) -> Evidence:
    return Evidence(
        surface="host:mac/disk",
        observation=Observation.FAULT,
        method=method,
        summary="2 days of runway at -20GB/day",
        source="shutil.disk_usage('/')",
        read_at=READ_AT,
        detail={"free_gb": 50.0},
    )


class TestTheMethodIsNeverUpgraded:
    def test_no_method_gains_trust_on_arrival(self):
        for claimed in Method:
            assert trust(arrival_method(claimed)) <= trust(claimed)

    def test_the_arrival_mapping_is_not_the_identity_function(self):
        """The mutation guard for this task's central rule.

        Every method the collector can claim that outranks a bare report is
        strictly downgraded. Replacing :func:`arrival_method` with ``lambda
        m: m`` — or dropping the call at the ingest boundary — fails here.
        """
        stronger_than_a_report = [m for m in Method if trust(m) > trust(Method.REPORTED)]

        assert stronger_than_a_report, "the trust ladder has collapsed"
        for claimed in stronger_than_a_report:
            assert trust(arrival_method(claimed)) < trust(claimed)

    def test_a_local_artifact_read_arrives_as_a_report(self):
        assert arrival_method(Method.LOCAL_ARTIFACT) is Method.REPORTED

    def test_the_mapping_is_total_over_method(self):
        """A method added later must be given an arrival grade deliberately.

        A ``dict.get(..., default)`` would silently grade an unconsidered
        method, which is how a future strong method sneaks through ungraded.
        """
        assert set(ON_ARRIVAL) == set(Method)

    def test_the_claimed_method_is_preserved_rather_than_erased(self):
        arrived = on_arrival(_evidence(Method.DESTINATION_API), "mac-studio", RECEIVED)

        assert arrived.method is Method.REPORTED
        assert arrived.detail[REPORTED_METHOD] == Method.DESTINATION_API.value


class TestArrivalAnnotation:
    def test_the_row_carries_the_collector_and_an_arrival_time(self):
        arrived = on_arrival(_evidence(), "mac-studio", RECEIVED)

        assert arrived.detail[COLLECTOR_ID] == "mac-studio"
        assert arrived.detail[RECEIVED_AT] == RECEIVED.isoformat()

    def test_arrival_time_is_a_distinct_field_from_read_at(self):
        """When we heard it and when it was seen are different facts.

        Collapsing them would date every observation to delivery time, and a
        spool delivered after an outage would then read as a burst of fresh
        readings taken during the outage.
        """
        arrived = on_arrival(_evidence(), "mac-studio", RECEIVED)

        assert arrived.read_at == READ_AT
        assert arrived.detail[RECEIVED_AT] != arrived.read_at.isoformat()

    def test_the_collectors_own_detail_survives_alongside_the_annotation(self):
        arrived = on_arrival(_evidence(), "mac-studio", RECEIVED)

        assert arrived.detail["free_gb"] == 50.0

    def test_surface_summary_source_and_observation_are_untouched(self):
        original = _evidence()

        arrived = on_arrival(original, "mac-studio", RECEIVED)

        assert arrived.surface == original.surface
        assert arrived.summary == original.summary
        assert arrived.source == original.source
        assert arrived.observation is original.observation

    def test_the_wire_row_id_identifies_the_observation_not_our_bookkeeping(self):
        """Identity belongs to what the collector saw.

        Two deliveries of one observation differ in arrival time and so hash
        differently as stored rows; the wire id is what lets ingest and any
        later reader still recognise them as one observation.
        """
        original = _evidence()
        first = on_arrival(original, "mac-studio", RECEIVED)
        second = on_arrival(
            original, "mac-studio", datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)
        )

        assert first.detail[WIRE_ROW_ID] == row_id(original)
        assert first.detail[WIRE_ROW_ID] == second.detail[WIRE_ROW_ID]
        assert first.detail[RECEIVED_AT] != second.detail[RECEIVED_AT]

    def test_annotating_twice_is_stable(self):
        """Ingest must not be able to launder a relayed row into a fresh one."""
        once = on_arrival(_evidence(), "mac-studio", RECEIVED)
        twice = on_arrival(once, "mac-studio", RECEIVED)

        assert twice.method is Method.REPORTED
        assert twice.detail[REPORTED_METHOD] == Method.LOCAL_ARTIFACT.value
