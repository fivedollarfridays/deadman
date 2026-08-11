"""``POST /self-check`` wired into the app a server actually serves.

Three things this file has to prove, because they are DM2.6's whole point:

1. An unauthenticated trigger is rejected, and stores nothing — mirroring
   ``TestIngestRouting``'s "rejected and stored nothing" discipline.
2. Self-evidence a scheduled hit writes is read back through the store, not
   a filesystem — proved by two independent apps, each with its own
   ``StoreSelfEvidenceLog``, sharing nothing but one store. That is what a
   Cloud Run cold start actually looks like: a fresh instance that shares no
   memory or disk with the one that ran before it.
3. The endpoint is not the public board: ``GET /self-check`` and
   ``POST /`` are both refused.
"""

from __future__ import annotations

import io
import json

from conftest import TEST_SCHEDULER_SECRET

from deadman.evidence.model import Evidence, Method, Observation
from deadman.scheduled.auth import AUTHORIZATION_ENVIRON_KEY
from deadman.scheduled.endpoint import SCHEDULED_PATH, ScheduledSelfCheckEndpoint
from deadman.self_check import SELF_CHECK_SURFACE, Liveness, StoreSelfEvidenceLog, self_check
from deadman.service import make_app
from deadman.store.memory import InMemoryEvidenceStore


def _call(app, path: str = "/", method: str = "GET", body: bytes | None = None, **extra: object):
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    environ: dict[str, object] = {"PATH_INFO": path, "REQUEST_METHOD": method}
    if body is not None:
        environ["CONTENT_LENGTH"] = str(len(body))
        environ["wsgi.input"] = io.BytesIO(body)
    environ.update(extra)
    payload = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], payload


def _evidence(surface: str, observation: Observation) -> Evidence:
    return Evidence(
        surface=surface,
        observation=observation,
        method=Method.LOCAL_ARTIFACT,
        summary=f"{surface}: {observation.value}",
        source="test",
    )


class _FakeProbe:
    def __init__(self, evidence: Evidence) -> None:
        self._evidence = evidence

    @property
    def surface(self) -> str:
        return self._evidence.surface

    @property
    def question(self) -> str:
        return "is it fine?"

    def observe(self) -> Evidence:
        return self._evidence


def _scheduled(store: InMemoryEvidenceStore, probes=None, secret: str = TEST_SCHEDULER_SECRET):
    return ScheduledSelfCheckEndpoint(
        probes_fn=lambda: probes or [],
        self_log=StoreSelfEvidenceLog(store=store),
        secret=secret,
    )


def _app(store: InMemoryEvidenceStore, probes=None, secret: str = TEST_SCHEDULER_SECRET):
    return make_app(lambda: [], scheduled=_scheduled(store, probes=probes, secret=secret))


class TestUnauthenticatedTriggersAreRejected:
    def test_a_request_with_no_authorization_header_is_401(self):
        store = InMemoryEvidenceStore()

        status, _headers, _body = _call(_app(store), SCHEDULED_PATH, method="POST")

        assert status.startswith("401")

    def test_a_wrong_bearer_token_is_401(self):
        store = InMemoryEvidenceStore()

        status, _headers, _body = _call(
            _app(store),
            SCHEDULED_PATH,
            method="POST",
            **{AUTHORIZATION_ENVIRON_KEY: "Bearer wrong-secret"},
        )

        assert status.startswith("401")

    def test_a_rejected_trigger_stores_nothing(self):
        store = InMemoryEvidenceStore()

        _call(_app(store), SCHEDULED_PATH, method="POST")

        assert store.latest_per_surface() == {}

    def test_the_response_is_still_json(self):
        store = InMemoryEvidenceStore()

        _status, headers, body = _call(_app(store), SCHEDULED_PATH, method="POST")

        assert dict(headers)["Content-Type"] == "application/json"
        assert "error" in json.loads(body)


class TestASuccessfulTriggerRecordsThroughTheStore:
    def _headers(self, secret: str = TEST_SCHEDULER_SECRET) -> dict[str, str]:
        return {AUTHORIZATION_ENVIRON_KEY: f"Bearer {secret}"}

    def test_a_correctly_authenticated_trigger_is_200(self):
        store = InMemoryEvidenceStore()

        status, _headers, _body = _call(
            _app(store), SCHEDULED_PATH, method="POST", **self._headers()
        )

        assert status == "200 OK"

    def test_a_successful_trigger_writes_a_row_on_the_self_check_surface(self):
        store = InMemoryEvidenceStore()

        _call(_app(store), SCHEDULED_PATH, method="POST", **self._headers())

        row = store.latest(SELF_CHECK_SURFACE)
        assert not row.is_blind

    def test_a_successful_trigger_sweeps_the_configured_probes(self):
        store = InMemoryEvidenceStore()
        probes = [_FakeProbe(_evidence("a", Observation.HEALTHY))]

        _status, _headers, body = _call(
            _app(store, probes=probes), SCHEDULED_PATH, method="POST", **self._headers()
        )

        payload = json.loads(body)
        assert payload["sweep_size"] == 1
        assert payload["blind_count"] == 0

    def test_self_check_against_the_store_reads_live_after_a_trigger(self):
        store = InMemoryEvidenceStore()

        _call(_app(store), SCHEDULED_PATH, method="POST", **self._headers())

        result = self_check(StoreSelfEvidenceLog(store=store), window_hours=30)
        assert result.liveness is Liveness.LIVE


class TestSelfEvidenceSurvivesACleanReadFromAnotherInstance:
    """The AC this class exists for: self-evidence is read from the store,
    not the filesystem, so it survives a cold start.

    Two apps, each built the way a fresh Cloud Run instance would build
    itself — its own ``ScheduledSelfCheckEndpoint``, its own
    ``StoreSelfEvidenceLog`` — sharing nothing but the one store object.
    Nothing here is in-memory state carried between the two; if the second
    app can see what the first wrote, it is only through the store.
    """

    def test_a_second_independently_built_app_reads_what_the_first_wrote(self):
        store = InMemoryEvidenceStore()
        first_instance = _app(store)
        second_instance = _app(store)
        headers = {AUTHORIZATION_ENVIRON_KEY: f"Bearer {TEST_SCHEDULER_SECRET}"}

        status, _headers, _body = _call(first_instance, SCHEDULED_PATH, method="POST", **headers)
        assert status == "200 OK"

        # The second "instance" never received a request; it only shares the
        # store. Its own fresh StoreSelfEvidenceLog must still read the row
        # the first instance wrote.
        result = self_check(StoreSelfEvidenceLog(store=store), window_hours=30)
        assert result.liveness is Liveness.LIVE

        # And a request handled by the second app instance sees the prior
        # trigger's evidence as its own "before" state.
        _status, _headers, body = _call(second_instance, SCHEDULED_PATH, method="POST", **headers)
        payload = json.loads(body)
        assert payload["liveness_before"] == Liveness.LIVE.value


class TestTheScheduledPathIsNotTheBoard:
    def test_get_on_the_scheduled_path_is_405_not_a_board(self):
        store = InMemoryEvidenceStore()

        status, _headers, _body = _call(_app(store), SCHEDULED_PATH, method="GET")

        assert status == "405 Method Not Allowed"

    def test_posting_to_the_board_path_is_still_405(self):
        store = InMemoryEvidenceStore()

        status, _headers, _body = _call(_app(store), "/", method="POST")

        assert status == "405 Method Not Allowed"

    def test_an_app_built_without_the_scheduled_endpoint_refuses_the_path(self):
        status, _headers, _body = _call(make_app(lambda: []), SCHEDULED_PATH, method="POST")

        assert status == "405 Method Not Allowed"

    def test_the_scheduled_path_never_reaches_default_probes_on_a_get(self):
        # A GET is refused before anything about probes or the store matters
        # — the endpoint the board wires in must never be reachable as a read.
        store = InMemoryEvidenceStore()

        _call(_app(store), SCHEDULED_PATH, method="GET")

        assert store.latest_per_surface() == {}
