"""The durable backoff is what production calls, proved through its wiring.

Nothing here constructs an alarm. Each sweep asks
:func:`deadman.service.default_scheduled` for the endpoint the deployed
service builds (``default_alarm`` from ``DEADMAN_ALERT_*``, the real
``default_probes``, real collector liveness from ``assess``) and triggers it
with an authenticated ``POST /self-check`` through the WSGI app. A new
endpoint is built for EVERY sweep over one persistent store, which is what a
Cloud Run cold start is. Replaced: the SMTP socket, and the endpoint's clock.

The fault is a declared collector that has never reported, because that row
comes out of the real liveness renderer and holds its state however long the
test's clock runs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from alarm_harness import ALERT_ENV, STORE_FACTORIES, Clock, install_fake_smtp
from conftest import TEST_SCHEDULER_SECRET

from deadman import service
from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest.arrival import on_arrival
from deadman.scheduled.auth import AUTHORIZATION_ENVIRON_KEY
from deadman.scheduled.endpoint import SCHEDULED_PATH
from deadman.verify.collector_liveness import assess
from deadman.verify.expectations import CollectorExpectation

SURFACE = "service:staging-queue"
COLLECTOR = "collector:rig"
EXPECTATIONS = (
    CollectorExpectation(collector_id="rig", interval_seconds=900.0, surfaces=(SURFACE,)),
)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch, tmp_path) -> list[str]:
    for name, value in ALERT_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(service.BRIEF_LOG_ENV, "")
    monkeypatch.setenv("DEADMAN_DISK_HISTORY", str(tmp_path / "disk-history.jsonl"))
    monkeypatch.delenv(service.COLLECTORS_ENV, raising=False)
    return install_fake_smtp(monkeypatch)


@pytest.fixture(params=sorted(STORE_FACTORIES))
def store(request: pytest.FixtureRequest):
    return STORE_FACTORIES[request.param]()


def _request(app, path: str, method: str) -> tuple[str, dict]:
    captured: dict[str, str] = {}
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        AUTHORIZATION_ENVIRON_KEY: f"Bearer {TEST_SCHEDULER_SECRET}",
    }
    body = b"".join(app(environ, lambda status, headers: captured.update(status=status)))
    return captured["status"], json.loads(body)


def _cold_app(store, clock: Clock):
    """A fresh instance: everything rebuilt from the environment but the store."""
    scheduled = service.default_scheduled(store, EXPECTATIONS)
    scheduled.clock = clock
    return service.make_app(
        service.default_probes,
        liveness_fn=lambda: assess(store, EXPECTATIONS),
        scheduled=scheduled,
        store=store,
    )


def _sweeps(store, clock: Clock, outbox: list[str], count: int) -> list[tuple[float, str]]:
    start, sent = clock.now, []
    for index in range(count):
        if index:
            clock.advance(15)
        before = len(outbox)
        status, payload = _request(_cold_app(store, clock), SCHEDULED_PATH, "POST")
        assert status.startswith("200"), payload
        assert payload["alerting"] == "active"
        elapsed = (clock.now - start).total_seconds() / 3600
        sent.extend((elapsed, body) for body in outbox[before:])
    return sent


def _about(sent: list[tuple[float, str]], needle: str) -> list[float]:
    return [hours for hours, body in sent if needle in body]


def test_a_fault_held_48_hours_through_the_deployed_wiring_sends_four_alerts(outbox, store):
    sent = _sweeps(store, Clock(), outbox, count=48 * 4 + 1)

    assert _about(sent, f"deadman: {COLLECTOR} is no_evidence") == [0, 6, 18, 42]
    assert _about(sent, f"deadman: {SURFACE} is no_evidence") == [0, 6, 18, 42]
    assert "held for 1d 18h" in sent[-1][1]


def test_the_send_record_is_not_a_surface_on_the_board(outbox, store):
    clock = Clock()
    _sweeps(store, clock, outbox, count=2)

    status, board = _request(_cold_app(store, clock), "/", "GET")

    assert status.startswith("200")
    assert store.load_alert_state(COLLECTOR)["sends"] == 1
    assert set(board["undeclared_surfaces"]) <= {"self:sweep"}
    assert [row["surface"] for row in board["surfaces"]].count(COLLECTOR) == 1
    assert not any("alert" in row["surface"] for row in board["surfaces"])


def test_a_heal_through_the_deployed_wiring_sends_one_recovery_per_surface(outbox, store):
    """The collector's first real delivery, annotated by the real arrival
    path, heals both its own row and the surface it reports."""
    clock = Clock()
    _sweeps(store, clock, outbox, count=3)
    arrived = datetime.now(timezone.utc)
    reading = Evidence(
        surface=SURFACE,
        observation=Observation.HEALTHY,
        method=Method.LOCAL_ARTIFACT,
        summary="queue is draining",
        source="rig:queue",
        read_at=arrived,
    )
    store.append(on_arrival(reading, "rig", arrived))
    del outbox[:]

    clock.advance(15)
    sent = _sweeps(store, clock, outbox, count=3)

    assert sorted(body.split(" — ")[0] for _, body in sent) == [
        f"deadman: {COLLECTOR} recovered",
        f"deadman: {SURFACE} recovered",
    ]
    assert {hours for hours, _ in sent} == {0}
