"""Store-and-forward: evidence a delivery failed to ship is never dropped.

Nothing about a :class:`Spool` lives in process memory — every method reads
or writes the directory directly. That is not an implementation detail, it
is the property the durability AC is checking: a second ``Spool`` pointed at
the same path, built with no reference to the first, must see exactly what
the first one left behind. That is what "survives a restart" means for a
process with no other state.
"""

from __future__ import annotations

from datetime import datetime, timezone

from deadman.collector.spool import Spool
from deadman.evidence.model import Evidence, Method, Observation

READ_AT = datetime(2026, 8, 11, 6, 0, tzinfo=timezone.utc)


def _evidence(surface: str = "host:disk/") -> Evidence:
    return Evidence(
        surface=surface,
        observation=Observation.FAULT,
        method=Method.LOCAL_ARTIFACT,
        summary=f"{surface} is unhappy",
        source="test",
        read_at=READ_AT,
        detail={"free_gb": 1.0},
    )


class TestEnqueueAndPending:
    def test_an_empty_spool_has_nothing_pending(self, tmp_path):
        spool = Spool(path=tmp_path / "spool")

        assert spool.pending() == []

    def test_enqueuing_rows_makes_them_pending(self, tmp_path):
        spool = Spool(path=tmp_path / "spool")
        rows = (_evidence("host:disk/"), _evidence("cron:morning-brief"))

        spool.enqueue(rows)

        (item,) = spool.pending()
        assert item.rows == rows

    def test_enqueuing_no_rows_writes_nothing(self, tmp_path):
        spool = Spool(path=tmp_path / "spool")

        spool.enqueue(())

        assert spool.pending() == []
        assert not (tmp_path / "spool").exists()

    def test_multiple_batches_are_returned_oldest_first(self, tmp_path):
        spool = Spool(path=tmp_path / "spool")
        first = (_evidence("first"),)
        second = (_evidence("second"),)

        spool.enqueue(first, when=datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc))
        spool.enqueue(second, when=datetime(2026, 8, 11, 6, 0, tzinfo=timezone.utc))

        items = spool.pending()
        assert [item.rows[0].surface for item in items] == ["first", "second"]


class TestDrop:
    def test_dropping_a_delivered_batch_removes_it(self, tmp_path):
        spool = Spool(path=tmp_path / "spool")
        spool.enqueue((_evidence(),))
        (item,) = spool.pending()

        spool.drop(item)

        assert spool.pending() == []

    def test_dropping_one_batch_leaves_the_others(self, tmp_path):
        spool = Spool(path=tmp_path / "spool")
        spool.enqueue((_evidence("keep"),), when=datetime(2026, 8, 10, tzinfo=timezone.utc))
        spool.enqueue((_evidence("drop"),), when=datetime(2026, 8, 11, tzinfo=timezone.utc))
        items = spool.pending()
        to_drop = next(i for i in items if i.rows[0].surface == "drop")

        spool.drop(to_drop)

        (remaining,) = spool.pending()
        assert remaining.rows[0].surface == "keep"


class TestSurvivesRestart:
    def test_a_fresh_spool_instance_sees_what_a_prior_one_wrote(self, tmp_path):
        spool_path = tmp_path / "spool"
        first_process = Spool(path=spool_path)
        first_process.enqueue((_evidence("host:disk/"),))

        # No reference to first_process from here on: this is what a
        # restarted collector process actually does.
        second_process = Spool(path=spool_path)

        items = second_process.pending()
        assert len(items) == 1
        assert items[0].rows[0].surface == "host:disk/"

    def test_evidence_survives_round_tripping_through_disk_unchanged(self, tmp_path):
        spool = Spool(path=tmp_path / "spool")
        original = _evidence("host:disk/")
        spool.enqueue((original,))

        reloaded = Spool(path=tmp_path / "spool")
        (item,) = reloaded.pending()

        assert item.rows[0].surface == original.surface
        assert item.rows[0].observation == original.observation
        assert item.rows[0].method == original.method
        assert item.rows[0].read_at == original.read_at
        assert item.rows[0].detail == original.detail
