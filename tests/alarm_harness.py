"""The production alarm path, with only the socket and the clock replaced.

Tests that pin what the scheduled alarm *sends* build it exactly as the
deployed service does — :func:`deadman.scheduled.alerting.alarm_from_env`
over a :class:`~deadman.self_check.StoreSelfEvidenceLog`, triggered through
:class:`~deadman.scheduled.endpoint.ScheduledSelfCheckEndpoint.handle` — and
replace nothing but ``smtplib.SMTP`` (so no socket opens) and the endpoint's
clock (so a throttle window can be crossed without sleeping). The audit that
found the re-fault suppression found it because the throttle had only ever
been tested in isolation, behind a caller that does not exist in production.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import pytest
from conftest import TEST_SCHEDULER_SECRET
from firestore_double import FakeFirestoreClient

from deadman.evidence.model import Evidence, Method, Observation, unobservable
from deadman.scheduled.alerting import alarm_from_env
from deadman.scheduled.endpoint import ScheduledSelfCheckEndpoint
from deadman.self_check import StoreSelfEvidenceLog
from deadman.store import EvidenceStore, FirestoreEvidenceStore, InMemoryEvidenceStore

AUTHORIZED = {"HTTP_AUTHORIZATION": f"Bearer {TEST_SCHEDULER_SECRET}"}
T0 = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

#: Placeholder SMTP settings on reserved example domains; nothing resolves.
ALERT_ENV = {
    "DEADMAN_ALERT_SMTP_HOST": "smtp.alarm.example",
    "DEADMAN_ALERT_SMTP_PORT": "587",
    "DEADMAN_ALERT_SMTP_USER": "alarm-bot@alarm.example",
    "DEADMAN_ALERT_SMTP_PASSWORD": "not-a-real-password",
    "DEADMAN_ALERT_FROM": "alarm-bot@alarm.example",
    "DEADMAN_ALERT_TO": "operator@alarm.example",
}


class FakeSMTP:
    """Stands in for :class:`smtplib.SMTP`; records every delivered body."""

    sent: list[str] = []
    down: bool = False
    """Set by a test to make every delivery raise, as a dead mail rail does."""

    def __init__(self, host: str, port: int, timeout: float = 0) -> None:
        self.host = host

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        return None

    def send_message(self, msg: EmailMessage) -> None:
        if FakeSMTP.down:
            raise ConnectionError("smtp rail is down")
        FakeSMTP.sent.append(msg.get_content())


def install_fake_smtp(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch the SMTP class the real transport constructs; return the outbox."""
    FakeSMTP.sent = []
    FakeSMTP.down = False
    monkeypatch.setattr("deadman.remediate.transports.smtplib.SMTP", FakeSMTP)
    return FakeSMTP.sent


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: float) -> None:
        self.now += timedelta(minutes=minutes)


class StaticProbe:
    """A probe whose next answer the test sets."""

    def __init__(self, surface: str, observation: Observation = Observation.HEALTHY) -> None:
        self.surface = surface
        self.question = f"is {surface} fine?"
        self.observation = observation

    def observe(self) -> Evidence:
        if self.observation is Observation.UNOBSERVABLE:
            return unobservable(self.surface, "harness", "cannot see it")
        return Evidence(
            surface=self.surface,
            observation=self.observation,
            method=Method.LOCAL_ARTIFACT,
            summary=f"{self.surface} is {self.observation.value}",
            source="harness",
        )


#: Every backend the deployed service can run on. The Firestore one is the
#: real backend over the in-process client double, as in the contract suite.
STORE_FACTORIES: dict[str, Callable[[], EvidenceStore]] = {
    "memory": InMemoryEvidenceStore,
    "firestore": lambda: FirestoreEvidenceStore(client=FakeFirestoreClient()),
}


def production_endpoint(
    probes: list[StaticProbe],
    clock: Callable[[], datetime] | None = None,
    monitored: tuple[str, ...] = ("host:disk/",),
    store: EvidenceStore | None = None,
) -> ScheduledSelfCheckEndpoint:
    """The scheduled endpoint wired the way :func:`deadman.service.default_scheduled` is.

    Every call builds a brand new alarm. Pass the same ``store`` to two calls
    and the second is what a cold start is: nothing shared but the store.
    """
    store = InMemoryEvidenceStore() if store is None else store
    extra = {} if clock is None else {"clock": clock}
    return ScheduledSelfCheckEndpoint(
        probes_fn=lambda: list(probes),
        self_log=StoreSelfEvidenceLog(store=store),
        secret=TEST_SCHEDULER_SECRET,
        alarm=alarm_from_env(store=store, monitored=list(monitored), environ=dict(ALERT_ENV)),
        **extra,
    )


def sweep_for(
    endpoint_for_sweep: Callable[[], ScheduledSelfCheckEndpoint],
    clock: Clock,
    outbox: list[str],
    hours: float,
    step_minutes: float = 15,
    before_sweep: Callable[[float], None] | None = None,
) -> list[tuple[float, str]]:
    """Trigger a sweep every ``step_minutes`` for ``hours`` (both ends
    included), asking ``endpoint_for_sweep`` for the endpoint each time so a
    test chooses between one warm instance and a cold start per sweep.
    ``before_sweep`` is told the hours elapsed, to change what a probe says.
    Returns ``(hours since the clock's start, body)`` for every mail sent."""
    start = clock.now
    sent: list[tuple[float, str]] = []
    for index in range(int(hours * 60 / step_minutes) + 1):
        if index:
            clock.advance(step_minutes)
        if before_sweep is not None:
            before_sweep((clock.now - start).total_seconds() / 3600)
        before = len(outbox)
        status, _ = endpoint_for_sweep().handle(dict(AUTHORIZED))
        assert status.startswith("200")
        elapsed = (clock.now - start).total_seconds() / 3600
        sent.extend((elapsed, body) for body in outbox[before:])
    return sent
