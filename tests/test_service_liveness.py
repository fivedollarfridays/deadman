"""The board, once it has to answer "is anyone still reporting".

The unit tests in ``tests/test_collector_liveness.py`` prove the verdicts.
These prove the verdicts reach the thing a human actually looks at — the gap
being closed is the one where liveness is perfect, nothing wires it into the
board, and the deployed service serves the same reassuring page it served
before anyone wrote any of it.

The last class here is an end-to-end pass: a collector's signed batch goes in
through ``POST /evidence`` and comes back out of ``GET /`` as a fresh surface.
Ingest and liveness must be holding the same store for that to work, and a
service that returns 200 to a delivery and then reports the sender silent
would be worse than one that never accepted it.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import TEST_INGEST_SECRET

from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest.arrival import on_arrival
from deadman.ingest.auth import SIGNATURE_ENVIRON_KEY, sign
from deadman.ingest.endpoint import EVIDENCE_PATH, IngestEndpoint
from deadman.ingest.wire import Batch, dumps
from deadman.service import COLLECTORS_ENV, build_board, default_expectations, make_app
from deadman.store.memory import InMemoryEvidenceStore
from deadman.verify.collector_liveness import assess, collector_surface
from deadman.verify.expectations import CollectorExpectation, ExpectationError

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)

DISK = "host:disk/"
BRIEF = "cron:morning-brief"
MAC = CollectorExpectation("kevin-mac", interval_seconds=900, surfaces=(DISK, BRIEF))


def _call(app, path: str = "/", method: str = "GET", body: bytes | None = None, **extra: object):
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status

    environ: dict[str, object] = {"PATH_INFO": path, "REQUEST_METHOD": method}
    if body is not None:
        environ["CONTENT_LENGTH"] = str(len(body))
        environ["wsgi.input"] = io.BytesIO(body)
    environ.update(extra)
    payload = b"".join(app(environ, start_response))
    return captured["status"], json.loads(payload)


def _delivered(surface: str, observation: Observation, read_at: datetime) -> Evidence:
    reading = Evidence(
        surface=surface,
        observation=observation,
        method=Method.LOCAL_ARTIFACT,
        summary=f"{surface} is {observation.value}",
        source="test",
        read_at=read_at,
    )
    return on_arrival(reading, "kevin-mac", read_at)


@pytest.fixture
def store() -> InMemoryEvidenceStore:
    return InMemoryEvidenceStore()


class TestTheBoardSeparatesNoFaultsFromNothingReported:
    def test_a_board_with_no_faults_and_no_reports_says_so_in_a_separate_count(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """The AC, stated as one assertion. Zero faults is not health when
        the reason there are no faults is that nothing has reported."""
        board = build_board([], liveness=assess(store, [MAC], NOW))

        assert board["fault_count"] == 1  # the collector itself, not the surfaces
        assert board["unreported_count"] == 2
        assert board["healthy_count"] == 0

    def test_the_three_surface_counts_partition_what_was_declared(
        self, store: InMemoryEvidenceStore
    ) -> None:
        store.append(_delivered(DISK, Observation.HEALTHY, NOW - timedelta(minutes=2)))
        store.append(_delivered(BRIEF, Observation.HEALTHY, NOW - timedelta(days=1)))

        board = build_board([], liveness=assess(store, [MAC], NOW))

        counts = (board["fresh_count"], board["stale_count"], board["unreported_count"])
        assert counts == (1, 1, 0)
        assert sum(counts) == len(MAC.surfaces)

    def test_a_board_built_without_liveness_declares_zero_collectors(self) -> None:
        """Rather than omitting the field, which would read as "fine"."""
        board = build_board([])

        assert board["collectors_declared"] == 0
        assert board["unreported_count"] == 0


class TestADeadCollectorIsOnTheBoard:
    def test_a_silent_collector_contributes_a_fault_row_naming_it(
        self, store: InMemoryEvidenceStore
    ) -> None:
        store.append(_delivered(DISK, Observation.HEALTHY, NOW - timedelta(hours=6)))

        board = build_board([], liveness=assess(store, [MAC], NOW))

        rows = {row["surface"]: row for row in board["surfaces"]}
        collector = rows[collector_surface("kevin-mac")]
        assert collector["observation"] == Observation.FAULT.value
        assert "kevin-mac" in collector["summary"]

    def test_its_stale_surfaces_are_blind_spots_not_healthy_rows(
        self, store: InMemoryEvidenceStore
    ) -> None:
        """A six-hour-old HEALTHY reading on a fifteen-minute cadence is not
        a healthy surface, and the board must not count it as one."""
        store.append(_delivered(DISK, Observation.HEALTHY, NOW - timedelta(hours=6)))

        board = build_board([], liveness=assess(store, [MAC], NOW))

        assert DISK in board["blind_spots"]
        assert board["healthy_count"] == 0

    def test_a_reporting_collector_leaves_its_fresh_surfaces_alone(
        self, store: InMemoryEvidenceStore
    ) -> None:
        store.append(_delivered(DISK, Observation.HEALTHY, NOW - timedelta(minutes=2)))
        store.append(_delivered(BRIEF, Observation.HEALTHY, NOW - timedelta(minutes=2)))

        board = build_board([], liveness=assess(store, [MAC], NOW))

        assert board["healthy_count"] == 3  # two surfaces plus the live collector
        assert board["fault_count"] == 0
        assert board["blind_spots"] == []

    def test_liveness_rows_join_the_local_sweep_rather_than_replacing_it(
        self, store: InMemoryEvidenceStore
    ) -> None:
        board = build_board([], liveness=assess(store, [MAC], NOW))

        assert {row["surface"] for row in board["surfaces"]} == {
            collector_surface("kevin-mac"),
            DISK,
            BRIEF,
        }

    def test_the_board_stays_json_serialisable_with_liveness_on_it(
        self, store: InMemoryEvidenceStore
    ) -> None:
        board = build_board([], liveness=assess(store, [MAC], NOW))

        assert json.dumps(board)


class TestTheAppReadsLivenessPerRequest:
    def test_every_request_recomputes_it(self, store: InMemoryEvidenceStore) -> None:
        """Silence accumulates between requests. A report computed once at
        startup would answer with how things were when the instance booted —
        and on Cloud Run, instances boot often."""
        calls: list[int] = []

        def liveness_fn():
            calls.append(1)
            return assess(store, [MAC], NOW)

        app = make_app(lambda: [], liveness_fn=liveness_fn)
        _call(app)
        _call(app)

        assert len(calls) == 2

    def test_a_board_without_a_liveness_fn_still_serves(self) -> None:
        status, board = _call(make_app(lambda: []))

        assert status == "200 OK"
        assert board["collectors_declared"] == 0


class TestDeclaringCollectorsAtStartup:
    def test_a_named_file_is_loaded(self, tmp_path: Path, monkeypatch) -> None:
        path = tmp_path / "collectors.json"
        path.write_text(
            json.dumps(
                {
                    "collectors": [
                        {"collector_id": "kevin-mac", "interval_seconds": 900, "surfaces": [DISK]}
                    ]
                }
            )
        )
        monkeypatch.setenv(COLLECTORS_ENV, str(path))

        (expectation,) = default_expectations()

        assert expectation.collector_id == "kevin-mac"

    def test_a_named_file_that_cannot_be_read_fails_startup(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Not a fallback to watching nobody. A liveness config with a typo in
        its path is a monitor that would discover its own blindness during the
        outage it failed to report."""
        monkeypatch.setenv(COLLECTORS_ENV, str(tmp_path / "absent.json"))

        with pytest.raises(ExpectationError):
            default_expectations()

    def test_an_unset_variable_warns_on_stderr(self, monkeypatch, capsys) -> None:
        """The consequence is invisible on the board, so it is stated where
        Cloud Run will capture it — the same bargain ``default_store`` makes
        for the forgetful backend."""
        monkeypatch.delenv(COLLECTORS_ENV, raising=False)

        assert default_expectations() == ()
        assert COLLECTORS_ENV in capsys.readouterr().err


class TestADeliveryReachesTheBoard:
    """The whole wire, end to end, in one test."""

    def test_a_posted_batch_turns_an_unreported_surface_into_a_fresh_one(self) -> None:
        store = InMemoryEvidenceStore()
        secret = TEST_INGEST_SECRET.encode()
        app = make_app(
            lambda: [],
            ingest=IngestEndpoint(store=store, secret=secret),
            liveness_fn=lambda: assess(store, [MAC]),
        )
        _status, before = _call(app)

        batch = Batch(
            collector_id="kevin-mac",
            signed_at=datetime.now(timezone.utc),
            rows=(
                Evidence(
                    surface=DISK,
                    observation=Observation.FAULT,
                    method=Method.LOCAL_ARTIFACT,
                    summary="2 days of runway",
                    source="shutil.disk_usage('/')",
                    read_at=datetime.now(timezone.utc),
                ),
            ),
        )
        body = dumps(batch)
        posted, _payload = _call(
            app,
            EVIDENCE_PATH,
            method="POST",
            body=body,
            **{SIGNATURE_ENVIRON_KEY: sign(body, secret)},
        )
        _status, after = _call(app)

        assert posted == "200 OK"
        assert before["unreported_count"] == 2
        assert (after["unreported_count"], after["fresh_count"]) == (1, 1)
        assert after["fault_count"] == 1  # the delivered fault; the collector is live now
