"""The wire format: what a collector ships and what the service reads back.

Everything here is about *not losing provenance in transit*. A wire format
that drops ``Method`` or flattens ``detail`` would turn a graded claim into an
ungraded one somewhere between the Mac and Cloud Run, and the loss would be
invisible: the row would still arrive, still name a surface, still say
"healthy". These tests pin the round trip field by field.

The other half is that the service parses input it did not write. Every
malformed shape below is a 4xx at the endpoint rather than a traceback, and
:class:`WireError` is what carries that distinction.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest.wire import Batch, WireError, dumps, loads

READ_AT = datetime(2026, 8, 11, 6, 56, tzinfo=timezone.utc)
SIGNED_AT = datetime(2026, 8, 11, 7, 0, tzinfo=timezone.utc)


def _evidence(**overrides: object) -> Evidence:
    fields: dict[str, object] = {
        "surface": "host:mac/disk",
        "observation": Observation.FAULT,
        "method": Method.LOCAL_ARTIFACT,
        "summary": "2 days of runway at -20GB/day",
        "source": "shutil.disk_usage('/')",
        "read_at": READ_AT,
        "detail": {"free_gb": 50.0, "slope_gb_per_day": -20.0, "trend": ["a", "b"]},
    }
    fields.update(overrides)
    return Evidence(**fields)  # type: ignore[arg-type]


def _batch(*rows: Evidence) -> Batch:
    return Batch(
        collector_id="mac-studio",
        signed_at=SIGNED_AT,
        rows=tuple(rows or (_evidence(),)),
    )


class TestRoundTrip:
    def test_a_batch_survives_the_wire_unchanged(self):
        batch = _batch()

        assert loads(dumps(batch)) == batch

    def test_method_and_detail_survive_verbatim(self):
        original = _evidence()

        restored = loads(dumps(_batch(original))).rows[0]

        assert restored.method is Method.LOCAL_ARTIFACT
        assert restored.observation is Observation.FAULT
        assert restored.detail == original.detail
        assert restored.read_at == READ_AT
        assert restored.provenance_row() == original.provenance_row()

    def test_every_method_round_trips(self):
        rows = tuple(_evidence(method=method, surface=f"s:{method.value}") for method in Method)

        restored = loads(dumps(_batch(*rows))).rows

        assert [row.method for row in restored] == list(Method)

    def test_the_signed_bytes_are_canonical(self):
        """Two batches equal by value serialise to identical bytes.

        The signature covers the bytes, so a serialiser whose key order
        depended on dict insertion would make a correctly signed batch fail
        verification depending on how the collector happened to build it.
        """
        assert dumps(_batch()) == dumps(loads(dumps(_batch())))

    def test_a_batch_of_no_rows_is_refused(self):
        """An empty batch is a collector that swept nothing claiming it
        reported, and DM2.4 reads arrival as liveness."""
        with pytest.raises(WireError):
            loads(dumps(Batch(collector_id="mac-studio", signed_at=SIGNED_AT, rows=())))


class TestMalformedInput:
    def test_bytes_that_are_not_json_raise_wire_error(self):
        with pytest.raises(WireError):
            loads(b"{not json")

    def test_a_json_array_is_not_a_batch(self):
        with pytest.raises(WireError):
            loads(b"[]")

    def test_a_row_missing_a_required_field_raises_wire_error(self):
        payload = json.loads(dumps(_batch()))
        del payload["rows"][0]["source"]

        with pytest.raises(WireError):
            loads(json.dumps(payload).encode())

    def test_an_unknown_method_raises_wire_error_rather_than_defaulting(self):
        """A method the service does not know is not quietly the weakest one.

        Coercing it would let a future collector's vocabulary arrive as a
        silently re-graded claim; refusing makes the version skew visible.
        """
        payload = json.loads(dumps(_batch()))
        payload["rows"][0]["method"] = "vibes"

        with pytest.raises(WireError):
            loads(json.dumps(payload).encode())

    def test_an_unparseable_read_at_raises_wire_error(self):
        payload = json.loads(dumps(_batch()))
        payload["rows"][0]["read_at"] = "yesterday"

        with pytest.raises(WireError):
            loads(json.dumps(payload).encode())

    def test_a_detail_that_is_not_an_object_raises_wire_error(self):
        payload = json.loads(dumps(_batch()))
        payload["rows"][0]["detail"] = ["free_gb", 50.0]

        with pytest.raises(WireError):
            loads(json.dumps(payload).encode())

    def test_a_missing_collector_id_raises_wire_error(self):
        payload = json.loads(dumps(_batch()))
        del payload["collector_id"]

        with pytest.raises(WireError):
            loads(json.dumps(payload).encode())

    def test_more_rows_than_the_cap_raises_wire_error(self):
        from deadman.ingest.wire import MAX_ROWS

        payload = json.loads(dumps(_batch()))
        payload["rows"] = payload["rows"] * (MAX_ROWS + 1)

        with pytest.raises(WireError):
            loads(json.dumps(payload).encode())
