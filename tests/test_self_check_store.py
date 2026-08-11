"""Store-backed self-evidence: proves a sweep happened without a
per-instance filesystem, so the claim survives a cold start.

DM1.11's ``SelfEvidenceLog`` proves the liveness of *an instance* — Cloud
Run's filesystem is per-instance and ephemeral, so a fresh instance cannot
see what a prior one wrote. The whole point of ``StoreSelfEvidenceLog`` is
that two independent readers, sharing nothing but the store, see the same
thing — because on Cloud Run the writer and the reader really are two
different processes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from deadman.self_check import (
    SELF_CHECK_SURFACE,
    Liveness,
    StoreSelfEvidenceLog,
    self_check,
)
from deadman.store.memory import InMemoryEvidenceStore


def test_record_then_latest_round_trips_the_timestamp():
    log = StoreSelfEvidenceLog(store=InMemoryEvidenceStore())
    when = datetime(2026, 8, 10, 9, 30, tzinfo=timezone.utc)

    log.record(sweep_size=4, blind=1, when=when)

    assert log.latest() == when


def test_latest_is_none_when_nothing_was_ever_written():
    log = StoreSelfEvidenceLog(store=InMemoryEvidenceStore())

    assert log.latest() is None


def test_self_check_reads_liveness_from_the_store():
    log = StoreSelfEvidenceLog(store=InMemoryEvidenceStore())
    log.record(sweep_size=2, blind=0, when=datetime.now(timezone.utc) - timedelta(hours=1))

    result = self_check(log, window_hours=30)

    assert result.liveness is Liveness.LIVE


def test_a_sweep_older_than_the_window_is_stale():
    log = StoreSelfEvidenceLog(store=InMemoryEvidenceStore())
    log.record(sweep_size=2, blind=0, when=datetime.now(timezone.utc) - timedelta(hours=49))

    result = self_check(log, window_hours=30)

    assert result.liveness is Liveness.STALE


def test_a_second_reader_over_the_same_store_sees_what_the_first_wrote():
    # The cold-start proof at the sink level: two independent
    # StoreSelfEvidenceLog instances, sharing nothing but the store, must
    # agree, because on Cloud Run the instance that wrote a row and the
    # instance asked to check it are not, in general, the same process.
    store = InMemoryEvidenceStore()
    writer = StoreSelfEvidenceLog(store=store)
    reader = StoreSelfEvidenceLog(store=store)

    writer.record(sweep_size=3, blind=1, when=datetime.now(timezone.utc) - timedelta(minutes=5))

    assert reader.latest() == writer.latest()
    assert self_check(reader, window_hours=30).liveness is Liveness.LIVE


def test_the_recorded_row_carries_sweep_size_and_blind_in_detail():
    store = InMemoryEvidenceStore()
    log = StoreSelfEvidenceLog(store=store)

    log.record(sweep_size=5, blind=2)

    row = store.latest(SELF_CHECK_SURFACE)
    assert row.detail["sweep_size"] == 5
    assert row.detail["blind"] == 2


def test_a_fresh_store_with_nothing_written_is_no_evidence():
    result = self_check(StoreSelfEvidenceLog(store=InMemoryEvidenceStore()), window_hours=30)

    assert result.liveness is Liveness.NO_EVIDENCE
