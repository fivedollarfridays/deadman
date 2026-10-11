"""The board carries only real surfaces (DM4.2).

Three rows of clutter were on the live board. ``host:disk/`` was the Cloud Run
container's own disk (1,001 GB free, 100 million days of runway): true and
useless, while the real disk is ``host:mac/disk`` from the collector. And
``undeclared_surfaces`` listed ``self:sweep``, a surface the service itself
writes and already judges in the ``self_check`` field.

Everything here goes through the app the service builds: the real
``default_probes``, real liveness from ``assess``, the real arrival
annotation, and ``default_scheduled`` for the alarm.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alarm_harness import ALERT_ENV, install_fake_smtp
from conftest import TEST_SCHEDULER_SECRET

from deadman import service
from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest.arrival import on_arrival
from deadman.probes.disk import DiskProbe
from deadman.scheduled.auth import AUTHORIZATION_ENVIRON_KEY
from deadman.scheduled.endpoint import SCHEDULED_PATH
from deadman.self_check import SELF_CHECK_SURFACE
from deadman.store.memory import InMemoryEvidenceStore
from deadman.verify.collector_liveness import assess
from deadman.verify.expectations import CollectorExpectation

REAL_DISK = "host:mac/disk"
EXPECTATIONS = (
    CollectorExpectation(collector_id="kevin-mac", interval_seconds=900.0, surfaces=(REAL_DISK,)),
)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    for name, value in ALERT_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(service.BRIEF_LOG_ENV, "")
    monkeypatch.delenv(service.COLLECTORS_ENV, raising=False)
    return install_fake_smtp(monkeypatch)


def _healthy_estate() -> InMemoryEvidenceStore:
    """One collector that just delivered a healthy reading of the real disk."""
    now = datetime.now(timezone.utc)
    reading = Evidence(
        surface=REAL_DISK,
        observation=Observation.HEALTHY,
        method=Method.LOCAL_ARTIFACT,
        summary="412.0GB free, 41.2% free",
        source="statvfs:/",
        read_at=now,
    )
    store = InMemoryEvidenceStore()
    store.append(on_arrival(reading, "kevin-mac", now))
    return store


def _app(store: InMemoryEvidenceStore):
    return service.make_app(
        service.default_probes,
        liveness_fn=lambda: assess(store, EXPECTATIONS),
        scheduled=service.default_scheduled(store, EXPECTATIONS),
        store=store,
    )


def _request(app, path: str, method: str) -> tuple[str, dict]:
    captured: dict[str, str] = {}
    environ = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        AUTHORIZATION_ENVIRON_KEY: f"Bearer {TEST_SCHEDULER_SECRET}",
    }
    body = b"".join(app(environ, lambda status, headers: captured.update(status=status)))
    return captured["status"], json.loads(body)


class TestTheInContainerDiskProbeCanBeSwitchedOff:
    def test_an_empty_disk_history_drops_the_probe(self, monkeypatch):
        monkeypatch.setenv(service.DISK_HISTORY_ENV, "")

        assert not any(isinstance(p, DiskProbe) for p in service.default_probes())

    def test_unset_keeps_the_probe_exactly_as_before(self, monkeypatch):
        monkeypatch.delenv(service.DISK_HISTORY_ENV, raising=False)

        (disk,) = [p for p in service.default_probes() if isinstance(p, DiskProbe)]

        assert service.DISK_HISTORY_ENV == "DEADMAN_DISK_HISTORY"
        assert disk.surface == "host:disk/"
        assert disk.history_path == Path("/tmp/deadman/disk-history.jsonl")

    def test_a_configured_path_reaches_the_probe_verbatim(self, monkeypatch, tmp_path):
        monkeypatch.setenv(service.DISK_HISTORY_ENV, str(tmp_path / "history.jsonl"))

        (disk,) = [p for p in service.default_probes() if isinstance(p, DiskProbe)]

        assert disk.history_path == tmp_path / "history.jsonl"

    def test_switched_off_the_board_has_no_row_and_no_blind_spot_for_it(self, monkeypatch, outbox):
        monkeypatch.setenv(service.DISK_HISTORY_ENV, "")

        status, board = _request(_app(_healthy_estate()), "/", "GET")

        assert status.startswith("200")
        assert [row["surface"] for row in board["surfaces"]] == ["collector:kevin-mac", REAL_DISK]
        assert board["blind_spots"] == []
        assert board["blind_count"] == 0
        assert board["fault_count"] == 0
        assert board["healthy_count"] == 2

    def test_switched_off_the_alarm_does_not_page_about_its_absence(self, monkeypatch, outbox):
        monkeypatch.setenv(service.DISK_HISTORY_ENV, "")
        app = _app(_healthy_estate())

        for _ in range(2):
            status, payload = _request(app, SCHEDULED_PATH, "POST")

            assert status.startswith("200")
            assert payload["alerting"] == "active"
            assert payload["sweep_size"] == 0
            assert payload["alerts_evaluated"] == 0
        assert outbox == []


class TestUndeclaredSurfacesListsOnlyWhatNobodyOwns:
    def test_the_services_own_sweep_is_not_undeclared_and_a_stray_surface_still_is(
        self, monkeypatch, outbox
    ):
        """``self:sweep`` is written by the real scheduled trigger, and a row
        for a surface no collector declares is stored beside it."""
        monkeypatch.setenv(service.DISK_HISTORY_ENV, "")
        store = _healthy_estate()
        app = _app(store)
        _request(app, SCHEDULED_PATH, "POST")
        store.append(
            Evidence(
                surface="smoke:deploy-check",
                observation=Observation.HEALTHY,
                method=Method.REPORTED,
                summary="end to end proof",
                source="smoke",
            )
        )

        _, board = _request(app, "/", "GET")

        assert not store.latest(SELF_CHECK_SURFACE).is_blind
        assert board["undeclared_surfaces"] == ["smoke:deploy-check"]
        assert board["self_check"]["liveness"] == "live"

    def test_with_nothing_stray_the_list_is_empty(self, monkeypatch, outbox):
        monkeypatch.setenv(service.DISK_HISTORY_ENV, "")
        app = _app(_healthy_estate())
        _request(app, SCHEDULED_PATH, "POST")

        _, board = _request(app, "/", "GET")

        assert board["undeclared_surfaces"] == []


class TestNoBoardFieldWasRenamedOrRemoved:
    """Another repository reads this JSON. These are the names it was built
    against; a field may be added, never renamed or dropped."""

    def test_the_top_level_keys_and_the_self_check_keys_are_pinned(self, monkeypatch, outbox):
        monkeypatch.setenv(service.DISK_HISTORY_ENV, "")
        app = _app(_healthy_estate())
        _request(app, SCHEDULED_PATH, "POST")

        _, board = _request(app, "/", "GET")

        assert set(board) == {
            "surfaces",
            "blind_spots",
            "healthy_count",
            "fault_count",
            "blind_count",
            "collectors_declared",
            "fresh_count",
            "stale_count",
            "unreported_count",
            "undeclared_surfaces",
            "self_check",
        }
        assert set(board["self_check"]) == {
            "surface",
            "liveness",
            "last_run_at",
            "age_seconds",
            "window_seconds",
            "interval_seconds",
        }

    def test_the_row_fields_a_reader_depends_on_are_still_there(self, monkeypatch, outbox):
        monkeypatch.setenv(service.DISK_HISTORY_ENV, "")

        _, board = _request(_app(_healthy_estate()), "/", "GET")

        collector, disk = board["surfaces"]
        row_keys = {
            "surface",
            "observation",
            "method",
            "summary",
            "source",
            "read_at",
            "detail",
            "held_since",
            "held_seconds",
        }
        assert row_keys <= set(collector)
        assert row_keys | {"reported_by"} <= set(disk)
        assert collector["detail"]["last_report_at"]
        assert collector["detail"]["liveness"] == "live"
