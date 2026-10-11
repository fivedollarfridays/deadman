"""Real transport, real failure evidence.

DM1.11 built ``AlertChannel`` with a construction-time refusal to sit on a
watched rail, but nothing real was ever wired to it: no transport actually
sent anything, the "monitored" list in its own tests was a hand-typed
literal, and a failed send had nowhere to go but an exception nobody
recorded. This suite proves the real pieces: an email transport over the same
SMTP rail ``ops/lib/email_send.py`` already uses, the out-of-band check
running against the actual probe list instead of a retyped copy of it, and a
failed send recorded as evidence before it propagates.

How often a persisting fault repeats is not decided by the transport; see
``tests/test_alarm_backoff_schedule.py``.
"""

from __future__ import annotations

import dataclasses

import pytest

from deadman.evidence.model import Observation
from deadman.remediate.alert import AlertChannel, AlertChannelInvalid
from deadman.remediate.transports import (
    ALERT_TRANSPORT_FAILURE_SURFACE,
    EmailTransport,
    EmailTransportNotConfigured,
    email_transport_from_env,
    real_monitored_surfaces,
    record_transport_failures,
)
from deadman.store.memory import InMemoryEvidenceStore

ENV = {
    "DEADMAN_ALERT_SMTP_HOST": "smtp.example.test",
    "DEADMAN_ALERT_SMTP_PORT": "587",
    "DEADMAN_ALERT_SMTP_USER": "alerts@example.test",
    "DEADMAN_ALERT_SMTP_PASSWORD": "hunter2",
    "DEADMAN_ALERT_FROM": "alerts@example.test",
    "DEADMAN_ALERT_TO": "kevin@example.test",
}


class _FakeSmtp:
    """Records what would have gone over the wire. Opens no socket, so this
    exercises message construction without needing ``allow_network``."""

    instances: list["_FakeSmtp"] = []

    def __init__(self, host, port, timeout=30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = None
        self.sent = []
        _FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


class _RaisingSmtp(_FakeSmtp):
    def send_message(self, msg):
        raise OSError("connection refused")


@pytest.fixture(autouse=True)
def _reset_fake_smtp():
    _FakeSmtp.instances.clear()
    yield
    _FakeSmtp.instances.clear()


def test_email_transport_sends_through_starttls_login_and_send_message():
    transport = EmailTransport(
        host="smtp.example.test",
        port=587,
        username="alerts@example.test",
        password="hunter2",
        from_addr="alerts@example.test",
        to_addr="kevin@example.test",
        smtp_cls=_FakeSmtp,
    )

    transport.send("disk runway 3 days")

    [smtp] = _FakeSmtp.instances
    assert (smtp.host, smtp.port) == ("smtp.example.test", 587)
    assert smtp.started_tls
    assert smtp.logged_in == ("alerts@example.test", "hunter2")
    [msg] = smtp.sent
    assert msg["To"] == "kevin@example.test"
    assert msg["From"] == "alerts@example.test"
    assert msg.get_content().strip() == "disk runway 3 days"


def test_a_transport_failure_propagates_rather_than_being_swallowed():
    transport = EmailTransport(
        host="smtp.example.test",
        port=587,
        username="u",
        password="p",
        from_addr="a@example.test",
        to_addr="b@example.test",
        smtp_cls=_RaisingSmtp,
    )

    with pytest.raises(OSError):
        transport.send("fault")


def test_email_transport_from_env_reads_every_field():
    transport = email_transport_from_env(ENV)

    assert transport.host == "smtp.example.test"
    assert transport.port == 587
    assert transport.username == "alerts@example.test"
    assert transport.password == "hunter2"
    assert transport.from_addr == "alerts@example.test"
    assert transport.to_addr == "kevin@example.test"


@pytest.mark.parametrize("missing", sorted(ENV))
def test_email_transport_from_env_refuses_when_any_variable_is_missing(missing):
    partial = {k: v for k, v in ENV.items() if k != missing}

    with pytest.raises(EmailTransportNotConfigured) as exc:
        email_transport_from_env(partial)

    assert missing in str(exc.value)


def test_email_transport_has_no_hardcoded_credential_defaults():
    # A caller that forgets to supply credentials must fail loudly at
    # construction rather than silently getting an empty-string default.
    fields = {f.name: f for f in dataclasses.fields(EmailTransport)}
    for name in ("host", "username", "password", "from_addr", "to_addr"):
        assert fields[name].default is dataclasses.MISSING


def test_real_monitored_surfaces_reflects_the_actual_probes_not_a_literal():
    surfaces = real_monitored_surfaces()

    assert "host:disk/" in surfaces
    assert "cron:morning-brief" in surfaces


def test_wiring_the_alarm_to_a_real_monitored_rail_raises_at_construction():
    with pytest.raises(AlertChannelInvalid):
        AlertChannel(
            transport="cron:morning-brief",
            send=lambda message: None,
            monitored=real_monitored_surfaces(),
        )


def test_an_email_transport_is_out_of_band_relative_to_the_real_list():
    channel = AlertChannel(
        transport="email:kevin@example.test",
        send=lambda message: None,
        monitored=real_monitored_surfaces(),
    )

    channel.alert("ok")  # does not raise


def test_a_transport_failure_is_recorded_as_evidence_rather_than_swallowed():
    store = InMemoryEvidenceStore()

    def failing_send(message: str) -> None:
        raise OSError("smtp said no")

    guarded = record_transport_failures(failing_send, store=store)

    with pytest.raises(OSError):
        guarded("deadman self-check stale")

    recorded = store.latest(ALERT_TRANSPORT_FAILURE_SURFACE)
    assert recorded.observation is Observation.FAULT
    assert "smtp said no" in recorded.summary
    assert recorded.detail["message"] == "deadman self-check stale"


def test_a_successful_send_records_nothing():
    store = InMemoryEvidenceStore()
    sent = []
    guarded = record_transport_failures(sent.append, store=store)

    guarded("all clear")

    assert sent == ["all clear"]
    assert store.latest(ALERT_TRANSPORT_FAILURE_SURFACE).observation is Observation.UNOBSERVABLE
