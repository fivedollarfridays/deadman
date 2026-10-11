"""When the alarm's own bookkeeping fails, it fails toward speaking.

A backoff that goes quiet because it could not read what it had already sent
is the self-concealing failure again, one layer down. So an unreadable send
record sends, and says so; nothing here is swallowed. Driven through the
scheduled endpoint with the alarm ``alarm_from_env`` builds.
"""

from __future__ import annotations

import pytest
from alarm_harness import (
    AUTHORIZED,
    Clock,
    FakeSMTP,
    StaticProbe,
    install_fake_smtp,
    production_endpoint,
    sweep_for,
)

from deadman.evidence.model import Observation
from deadman.remediate.transports import ALERT_TRANSPORT_FAILURE_SURFACE
from deadman.scheduled.backoff import ALERT_STATE_FAILURE_SURFACE
from deadman.store.memory import InMemoryEvidenceStore

SURFACE = "service:staging-queue"
MONITORED = (SURFACE,)


class _UnreadableSendRecord(InMemoryEvidenceStore):
    def load_alert_state(self, key: str):
        raise OSError("send record backend unavailable")


class _UnwritableSendRecord(InMemoryEvidenceStore):
    def save_alert_state(self, key: str, record) -> None:
        raise OSError("send record backend is read only")


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_fake_smtp(monkeypatch)


def _cold_sweeps(store, outbox, observation: Observation, hours: float):
    clock = Clock()
    probe = StaticProbe(SURFACE, observation)

    def cold() -> object:
        return production_endpoint([probe], clock=clock, monitored=MONITORED, store=store)

    return sweep_for(cold, clock, outbox, hours=hours)


def test_an_unreadable_send_record_sends_the_alert_and_records_the_failure(outbox):
    store = _UnreadableSendRecord()

    sent = _cold_sweeps(store, outbox, Observation.FAULT, hours=0.5)

    assert [hours for hours, _ in sent] == [0, 0.25, 0.5]
    assert all(f"deadman: {SURFACE} is fault" in body for _, body in sent)
    assert all("repeats are NOT being limited" in body for _, body in sent)
    failures = store.history(ALERT_STATE_FAILURE_SURFACE)
    assert len(failures) == 3
    assert {f.observation for f in failures} == {Observation.FAULT}
    assert failures[0].detail["key"] == SURFACE
    assert failures[0].detail["operation"] == "read"
    assert "send record backend unavailable" in failures[0].summary


def test_a_malformed_send_record_sends_once_then_is_replaced_by_a_good_one(outbox):
    """A document this code did not write is unreadable, not "no episode":
    it sends. The save after it repairs the record, so one bad document does
    not page on every sweep forever."""
    store = InMemoryEvidenceStore()
    store.save_alert_state(SURFACE, {"state": "fault", "sends": "many"})

    sent = _cold_sweeps(store, outbox, Observation.FAULT, hours=6)

    assert [hours for hours, _ in sent] == [0, 6]
    assert "repeats are NOT being limited" in sent[0][1]
    assert "repeats are NOT being limited" not in sent[1][1]
    assert len(store.history(ALERT_STATE_FAILURE_SURFACE)) == 1


def test_an_unreadable_send_record_on_a_healthy_surface_is_evidence_not_a_recovery(outbox):
    """It cannot know the surface ever alerted, and "recovered" for every
    healthy surface on every sweep would be an alarm about nothing."""
    store = _UnreadableSendRecord()

    sent = _cold_sweeps(store, outbox, Observation.HEALTHY, hours=0.25)

    assert sent == []
    failures = store.history(ALERT_STATE_FAILURE_SURFACE)
    assert len(failures) == 2
    assert failures[0].detail == {
        "key": SURFACE,
        "operation": "read",
        "error": "send record backend unavailable",
    }


def test_a_send_record_that_cannot_be_written_is_recorded_and_the_alert_still_went(outbox):
    store = _UnwritableSendRecord()

    sent = _cold_sweeps(store, outbox, Observation.FAULT, hours=0.25)

    assert [hours for hours, _ in sent] == [0, 0.25]  # nothing remembered, so it repeats
    failures = store.history(ALERT_STATE_FAILURE_SURFACE)
    assert [f.detail["operation"] for f in failures] == ["write", "write"]
    assert "could not be written" in failures[0].summary


def test_a_failed_send_is_not_recorded_as_sent_and_still_propagates(outbox):
    """Transport failure behaviour is unchanged (evidence, then the raise),
    and the backoff must not count the alert that never left: the next sweep
    sends it instead of waiting six hours."""
    store = InMemoryEvidenceStore()
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)

    FakeSMTP.down = True
    with pytest.raises(ConnectionError):
        production_endpoint([probe], clock=clock, monitored=MONITORED, store=store).handle(
            dict(AUTHORIZED)
        )

    assert store.load_alert_state(SURFACE) is None
    assert "alert transport failed" in store.latest(ALERT_TRANSPORT_FAILURE_SURFACE).summary

    FakeSMTP.down = False
    clock.advance(15)
    production_endpoint([probe], clock=clock, monitored=MONITORED, store=store).handle(
        dict(AUTHORIZED)
    )

    assert len(outbox) == 1
    assert "First alert for this state." in outbox[0]


def test_a_refault_after_a_recovery_notice_that_failed_to_send_still_alerts(outbox):
    """The episode is closed before the notice goes out, so a dead mail rail
    at the moment of the heal cannot turn the next fault into a "repeat"."""
    store = InMemoryEvidenceStore()
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)

    def sweep() -> None:
        production_endpoint([probe], clock=clock, monitored=MONITORED, store=store).handle(
            dict(AUTHORIZED)
        )
        clock.advance(15)

    sweep()
    probe.observation, FakeSMTP.down = Observation.HEALTHY, True
    with pytest.raises(ConnectionError):
        sweep()
    probe.observation, FakeSMTP.down = Observation.FAULT, False
    clock.advance(15)
    sweep()

    assert [body.count(f"{SURFACE} is fault") > 0 for body in outbox] == [True, True]


class _FlakySendRecord(InMemoryEvidenceStore):
    """Reads fail while ``reads_fail`` is set; writes are counted."""

    reads_fail = False
    writes = 0

    def load_alert_state(self, key: str):
        if self.reads_fail:
            raise OSError("send record backend unavailable")
        return super().load_alert_state(key)

    def save_alert_state(self, key: str, record) -> None:
        self.writes += 1
        super().save_alert_state(key, record)


def test_a_transient_read_failure_during_a_heal_does_not_lose_the_recovery_notice(outbox):
    """The episode is real and open. One failed read on the heal sweep must
    leave it exactly as it was, so the next healthy sweep sends the notice."""
    store = _FlakySendRecord()
    clock = Clock()
    probe = StaticProbe(SURFACE, Observation.FAULT)

    def sweep() -> None:
        production_endpoint([probe], clock=clock, monitored=MONITORED, store=store).handle(
            dict(AUTHORIZED)
        )
        clock.advance(15)

    sweep()
    opened = store.load_alert_state(SURFACE)
    writes_before = store.writes

    probe.observation, store.reads_fail = Observation.HEALTHY, True
    sweep()

    store.reads_fail = False
    assert [body for body in outbox if "recovered" in body] == []
    assert store.writes == writes_before
    assert store.load_alert_state(SURFACE) == opened
    (failure,) = store.history(ALERT_STATE_FAILURE_SURFACE)
    assert failure.detail["key"] == SURFACE
    assert failure.detail["operation"] == "read"

    sweep()
    sweep()

    recoveries = [body for body in outbox if "recovered" in body]
    assert len(recoveries) == 1, outbox
    assert store.load_alert_state(SURFACE)["open"] is False


def test_a_malformed_record_on_a_healthy_surface_never_mails_and_is_left_alone(outbox):
    """It sends nothing, on any sweep: no page, no recovery notice. Each sweep
    records the failure; the record is repaired the next time the surface
    alerts, which is the first moment it matters."""
    store = InMemoryEvidenceStore()
    malformed = {"state": "fault", "sends": "many"}
    store.save_alert_state(SURFACE, malformed)

    sent = _cold_sweeps(store, outbox, Observation.HEALTHY, hours=1)

    assert sent == []
    assert store.load_alert_state(SURFACE) == malformed
    failures = store.history(ALERT_STATE_FAILURE_SURFACE)
    assert len(failures) == 5
    assert {f.detail["operation"] for f in failures} == {"read"}

    repaired = _cold_sweeps(store, outbox, Observation.FAULT, hours=0.5)

    assert [hours for hours, _ in repaired] == [0]
    assert store.load_alert_state(SURFACE)["open"] is True
