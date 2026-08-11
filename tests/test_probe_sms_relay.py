"""Locks the SMS relay probe's active-canary behaviour.

The relay and its sent folder are both injected, and ``tests/conftest.py``
blocks sockets suite-wide anyway, so nothing here touches a real network or
sends a real text. The distinctions under test are the ones the acceptance
criteria name:

* no canary due this sweep is ``UNOBSERVABLE``, never ``HEALTHY``;
* a landed canary is ``HEALTHY`` only once the sent folder confirms it, not
  at dispatch acceptance;
* an unreachable relay host is ``UNOBSERVABLE``, distinct from a rejected
  send, which is ``FAULT``;
* cadence throttles repeated canaries and defaults to a conservative value.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from deadman.evidence.model import Method, Observation
from deadman.probes.base import run_probe
from deadman.probes.sms_relay import (
    DEFAULT_CADENCE_HOURS,
    DispatchOutcome,
    DispatchResult,
    SmsRelayProbe,
)


class _Relay:
    """Stands in for the phone/SMS relay. Records every token it was asked
    to send, so a test can assert whether a canary actually ran."""

    def __init__(self, outcome: DispatchOutcome, why: str = "") -> None:
        self._outcome = outcome
        self._why = why
        self.sent_tokens: list[str] = []

    def send_canary(self, token: str) -> DispatchResult:
        self.sent_tokens.append(token)
        return DispatchResult(outcome=self._outcome, why=self._why)


class _SentFolder:
    """Stands in for the destination sent folder."""

    def __init__(self, *, landed_tokens: set[str] | None = None) -> None:
        self._landed = landed_tokens or set()
        self.checked_tokens: list[str] = []

    def find(self, token: str) -> bool:
        self.checked_tokens.append(token)
        return token in self._landed


class _RaisingRelay:
    def send_canary(self, token: str) -> DispatchResult:
        raise ConnectionError("simulated transport failure")


class _RaisingSentFolder:
    def find(self, token: str) -> bool:
        raise TimeoutError("simulated read timeout")


def _probe(tmp_path: Path, **kwargs: object) -> SmsRelayProbe:
    kwargs.setdefault("history_path", tmp_path / "sms-canary-history.jsonl")
    kwargs.setdefault("token_factory", lambda: "canary-fixed")
    return SmsRelayProbe(**kwargs)  # type: ignore[arg-type]


# --- the three cases the acceptance criteria name --------------------------


def test_canary_confirmed_in_sent_folder_is_healthy_on_canary_evidence(
    tmp_path: Path,
) -> None:
    relay = _Relay(outcome=DispatchOutcome.ACCEPTED)
    sent_folder = _SentFolder(landed_tokens={"canary-fixed"})
    probe = _probe(tmp_path, relay=relay, sent_folder=sent_folder)

    evidence = probe.observe()

    assert evidence.observation is Observation.HEALTHY
    assert evidence.method is Method.ACTIVE_CANARY
    assert relay.sent_tokens == ["canary-fixed"]
    assert sent_folder.checked_tokens == ["canary-fixed"]


def test_unreachable_relay_host_is_unobservable_never_fault(tmp_path: Path) -> None:
    relay = _Relay(outcome=DispatchOutcome.UNREACHABLE, why="connection timed out")
    sent_folder = _SentFolder()
    probe = _probe(tmp_path, relay=relay, sent_folder=sent_folder)

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.FAULT
    assert evidence.detail["dispatch_outcome"] == "unreachable"
    # An unreachable host was never read, so there is nothing to verify.
    assert sent_folder.checked_tokens == []


def test_rejected_send_is_fault_distinct_from_unreachable(tmp_path: Path) -> None:
    relay = _Relay(outcome=DispatchOutcome.REJECTED, why="invalid destination number")
    sent_folder = _SentFolder()
    probe = _probe(tmp_path, relay=relay, sent_folder=sent_folder)

    evidence = probe.observe()

    assert evidence.observation is Observation.FAULT
    assert evidence.detail["dispatch_outcome"] == "rejected"
    assert "invalid destination number" in evidence.summary
    assert sent_folder.checked_tokens == []


# --- silence without a canary --------------------------------------------


def test_no_canary_due_yet_is_unobservable_never_healthy(tmp_path: Path) -> None:
    """The core guarantee: without a fresh canary this sweep, we have no
    evidence the rail is alive, and must not report otherwise."""
    history_path = tmp_path / "sms-canary-history.jsonl"
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    history_path.write_text(f'{{"ts": "{recent.isoformat()}", "token": "prior"}}\n')

    relay = _Relay(outcome=DispatchOutcome.ACCEPTED)
    sent_folder = _SentFolder(landed_tokens={"canary-fixed"})
    probe = _probe(
        tmp_path,
        relay=relay,
        sent_folder=sent_folder,
        history_path=history_path,
        cadence_hours=12.0,
    )

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.HEALTHY
    # No canary should have been sent while inside the cadence window.
    assert relay.sent_tokens == []
    assert sent_folder.checked_tokens == []


def test_a_first_ever_call_with_no_history_sends_a_canary(tmp_path: Path) -> None:
    """No history means no prior evidence at all, so the probe must actively
    check rather than silently reporting nothing."""
    relay = _Relay(outcome=DispatchOutcome.ACCEPTED)
    sent_folder = _SentFolder(landed_tokens={"canary-fixed"})
    probe = _probe(tmp_path, relay=relay, sent_folder=sent_folder)

    evidence = probe.observe()

    assert relay.sent_tokens == ["canary-fixed"]
    assert evidence.observation is Observation.HEALTHY


def test_a_canary_outside_the_cadence_window_is_due_again(tmp_path: Path) -> None:
    history_path = tmp_path / "sms-canary-history.jsonl"
    stale = datetime.now(timezone.utc) - timedelta(hours=13)
    history_path.write_text(f'{{"ts": "{stale.isoformat()}", "token": "prior"}}\n')

    relay = _Relay(outcome=DispatchOutcome.ACCEPTED)
    sent_folder = _SentFolder(landed_tokens={"canary-fixed"})
    probe = _probe(
        tmp_path,
        relay=relay,
        sent_folder=sent_folder,
        history_path=history_path,
        cadence_hours=12.0,
    )

    evidence = probe.observe()

    assert relay.sent_tokens == ["canary-fixed"]
    assert evidence.observation is Observation.HEALTHY


def test_cadence_default_is_conservative() -> None:
    # Twice a day at most, never on every sweep -- canaries are real sends.
    assert DEFAULT_CADENCE_HOURS >= 6.0


def test_cadence_is_configurable(tmp_path: Path) -> None:
    history_path = tmp_path / "sms-canary-history.jsonl"
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    history_path.write_text(f'{{"ts": "{recent.isoformat()}", "token": "prior"}}\n')

    relay = _Relay(outcome=DispatchOutcome.ACCEPTED)
    sent_folder = _SentFolder(landed_tokens={"canary-fixed"})
    probe = _probe(
        tmp_path,
        relay=relay,
        sent_folder=sent_folder,
        history_path=history_path,
        cadence_hours=0.5,
    )

    evidence = probe.observe()

    assert relay.sent_tokens == ["canary-fixed"]
    assert evidence.observation is Observation.HEALTHY


# --- dispatch accepted but never lands (dead rail) -------------------------


def test_canary_accepted_but_absent_from_sent_folder_is_fault(tmp_path: Path) -> None:
    relay = _Relay(outcome=DispatchOutcome.ACCEPTED)
    sent_folder = _SentFolder(landed_tokens=set())
    probe = _probe(tmp_path, relay=relay, sent_folder=sent_folder)

    evidence = probe.observe()

    assert evidence.observation is Observation.FAULT
    assert evidence.method is Method.ACTIVE_CANARY
    assert "canary-fixed" in evidence.summary
    assert evidence.detail["dispatch_outcome"] == "accepted"


# --- cadence throttles attempts, not just successes ------------------------


def test_an_unreachable_attempt_still_records_and_throttles_the_next_call(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "sms-canary-history.jsonl"
    relay = _Relay(outcome=DispatchOutcome.UNREACHABLE, why="dns failure")
    sent_folder = _SentFolder()
    probe = _probe(
        tmp_path,
        relay=relay,
        sent_folder=sent_folder,
        history_path=history_path,
        cadence_hours=12.0,
    )

    first = probe.observe()
    second = probe.observe()

    assert first.observation is Observation.UNOBSERVABLE
    assert second.observation is Observation.UNOBSERVABLE
    # Only the first call actually attempted a send; the second was throttled.
    assert relay.sent_tokens == ["canary-fixed"]
    assert "no canary due yet" in second.detail["reason"]


# --- never-raise contract ---------------------------------------------------


def test_a_raising_relay_is_unobservable_not_fault(tmp_path: Path) -> None:
    probe = _probe(tmp_path, relay=_RaisingRelay(), sent_folder=_SentFolder())

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.FAULT


def test_a_raising_sent_folder_reader_is_unobservable_not_fault(tmp_path: Path) -> None:
    relay = _Relay(outcome=DispatchOutcome.ACCEPTED)
    probe = _probe(tmp_path, relay=relay, sent_folder=_RaisingSentFolder())

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.FAULT


def test_a_raising_relay_is_contained_by_the_probe_contract(tmp_path: Path) -> None:
    probe = _probe(tmp_path, relay=_RaisingRelay(), sent_folder=_SentFolder())

    evidence = run_probe(probe)

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.surface == "sms:relay"


# --- identity ----------------------------------------------------------------


def test_the_surface_id_is_stable(tmp_path: Path) -> None:
    probe = _probe(
        tmp_path, relay=_Relay(outcome=DispatchOutcome.ACCEPTED), sent_folder=_SentFolder()
    )

    assert probe.surface == "sms:relay"
    assert probe.observe().surface == "sms:relay"
