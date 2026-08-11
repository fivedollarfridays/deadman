"""Tests for the Cloud Run service: the board it publishes.

No sockets: ``app`` is a plain WSGI callable, exercised in-process with a
fake ``environ``/``start_response`` pair, exactly like a real WSGI server
would call it, but with nothing bound to a port.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import pytest
from conftest import TEST_INGEST_SECRET

from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest.auth import SIGNATURE_ENVIRON_KEY, sign
from deadman.ingest.endpoint import EVIDENCE_PATH, IngestEndpoint
from deadman.ingest.wire import Batch, dumps
from deadman.service import (
    STORE_BACKEND_ENV,
    StoreMisconfigured,
    build_board,
    default_store,
    make_app,
)
from deadman.store.firestore import StoreSdkMissing
from deadman.store.memory import InMemoryEvidenceStore


def _evidence(surface: str, observation: Observation, **detail: object) -> Evidence:
    return Evidence(
        surface=surface,
        observation=observation,
        method=Method.LOCAL_ARTIFACT,
        summary=f"{surface}: {observation.value}",
        source="test",
        detail=detail,
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


class _RaisingProbe:
    surface = "host:broken"
    question = "does this probe explode?"

    def observe(self) -> Evidence:
        raise RuntimeError("boom")


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


def _signed_batch(secret: bytes) -> tuple[bytes, str]:
    batch = Batch(
        collector_id="mac-studio",
        signed_at=datetime.now(timezone.utc),
        rows=(_evidence("host:mac/disk", Observation.FAULT),),
    )
    body = dumps(batch)
    return body, sign(body, secret)


class TestBuildBoard:
    def test_counts_healthy_fault_and_blind_separately(self):
        probes = [
            _FakeProbe(_evidence("a", Observation.HEALTHY)),
            _FakeProbe(_evidence("b", Observation.FAULT)),
            _FakeProbe(_evidence("c", Observation.UNOBSERVABLE)),
        ]

        board = build_board(probes)

        assert board["healthy_count"] == 1
        assert board["fault_count"] == 1
        assert board["blind_count"] == 1
        assert board["blind_spots"] == ["c"]
        assert [row["surface"] for row in board["surfaces"]] == ["a", "b", "c"]

    def test_a_raising_probe_becomes_a_blind_spot_not_a_500(self):
        probes = [_FakeProbe(_evidence("a", Observation.HEALTHY)), _RaisingProbe()]

        board = build_board(probes)

        assert board["healthy_count"] == 1
        assert board["blind_count"] == 1
        assert "host:broken" in board["blind_spots"]

    def test_empty_probe_list_yields_an_empty_but_valid_board(self):
        board = build_board([])

        assert board == {
            "surfaces": [],
            "blind_spots": [],
            "healthy_count": 0,
            "fault_count": 0,
            "blind_count": 0,
        }

    def test_evidence_rows_are_json_serializable(self):
        probes = [_FakeProbe(_evidence("a", Observation.HEALTHY, free_gb=12.5))]

        board = build_board(probes)

        encoded = json.dumps(board)  # must not raise
        assert "free_gb" in encoded


class TestApp:
    def test_get_root_returns_200_with_the_board_as_json(self):
        probes = [_FakeProbe(_evidence("a", Observation.HEALTHY))]
        app = make_app(lambda: probes)

        status, headers, body = _call(app, "/")

        assert status == "200 OK"
        header_dict = dict(headers)
        assert header_dict["Content-Type"] == "application/json"
        payload = json.loads(body)
        assert payload["healthy_count"] == 1
        assert payload["surfaces"][0]["surface"] == "a"

    def test_probes_are_read_fresh_on_every_request(self):
        calls = {"n": 0}

        def probes_fn():
            calls["n"] += 1
            return [_FakeProbe(_evidence("a", Observation.HEALTHY))]

        app = make_app(probes_fn)

        _call(app, "/")
        _call(app, "/")

        assert calls["n"] == 2

    def test_non_get_method_is_rejected(self):
        app = make_app(lambda: [])

        status, headers, _body = _call(app, "/", method="POST")

        assert status == "405 Method Not Allowed"

    def test_default_app_is_importable_and_callable(self):
        from deadman.service import app as default_app

        status, _headers, body = _call(default_app, "/")

        assert status == "200 OK"
        payload = json.loads(body)
        assert "surfaces" in payload


class TestIngestRouting:
    """``POST /evidence`` is wired into the app a server actually serves.

    The gap these close: every ingest unit test can be green while nothing
    routes to the endpoint, which would ship a service that answers 405 to
    every collector in the estate and a board that never changes.
    """

    def _app(self, store: InMemoryEvidenceStore, secret: bytes = b"s3cret"):
        return make_app(lambda: [], ingest=IngestEndpoint(store=store, secret=secret))

    def test_a_signed_batch_posted_to_evidence_is_stored(self):
        store = InMemoryEvidenceStore()
        body, signature = _signed_batch(b"s3cret")

        status, headers, response = _call(
            self._app(store),
            EVIDENCE_PATH,
            method="POST",
            body=body,
            **{SIGNATURE_ENVIRON_KEY: signature},
        )

        assert status == "200 OK"
        assert dict(headers)["Content-Type"] == "application/json"
        assert json.loads(response)["stored"] == 1
        assert store.latest("host:mac/disk").observation is Observation.FAULT

    def test_an_unsigned_post_to_evidence_is_401_from_the_app(self):
        store = InMemoryEvidenceStore()
        body, _signature = _signed_batch(b"s3cret")

        status, _headers, _response = _call(self._app(store), EVIDENCE_PATH, "POST", body=body)

        assert status.startswith("401")
        assert store.latest_per_surface() == {}

    def test_getting_the_evidence_path_is_405_not_a_board(self):
        status, _headers, _body = _call(self._app(InMemoryEvidenceStore()), EVIDENCE_PATH)

        assert status == "405 Method Not Allowed"

    def test_posting_to_the_board_path_is_still_405(self):
        status, _headers, _body = _call(self._app(InMemoryEvidenceStore()), "/", method="POST")

        assert status == "405 Method Not Allowed"

    def test_an_app_built_without_ingest_refuses_the_path_rather_than_crashing(self):
        status, _headers, _body = _call(make_app(lambda: []), EVIDENCE_PATH, "POST", body=b"{}")

        assert status == "405 Method Not Allowed"

    def test_ingest_does_not_forge_liveness_for_a_service_that_never_swept(self):
        """A delivered batch is not a sweep.

        DM1.11's rule, one endpoint over: self-evidence is recorded when the
        board is served, because that is when probes ran. Recording it here
        would let a chatty collector keep a blind service looking alive.
        """
        recorded: list[tuple[int, int]] = []

        class _Log:
            def record(self, sweep_size: int, blind: int) -> None:
                recorded.append((sweep_size, blind))

        store = InMemoryEvidenceStore()
        app = make_app(
            lambda: [],
            self_log=_Log(),
            ingest=IngestEndpoint(store=store, secret=b"s3cret"),
        )
        body, signature = _signed_batch(b"s3cret")

        _call(app, EVIDENCE_PATH, "POST", body=body, **{SIGNATURE_ENVIRON_KEY: signature})

        assert recorded == []

        _call(app, "/")

        assert recorded == [(0, 0)]


class TestDefaultStore:
    """Which backend ingested evidence lands in, and whether that is loud.

    The forgetful backend is the right default for a local run and a false
    green on Cloud Run: instances are ephemeral, so a memory-backed deploy
    answers ``stored: 1`` to a collector whose spool will not survive the next
    scale-to-zero. That is the exact shape of lie this project is about, so it
    does not get to happen quietly.
    """

    def test_the_default_is_memory_and_it_says_so_on_stderr(self, monkeypatch, capsys):
        monkeypatch.delenv(STORE_BACKEND_ENV, raising=False)

        store = default_store()

        assert isinstance(store, InMemoryEvidenceStore)
        assert STORE_BACKEND_ENV in capsys.readouterr().err

    def test_an_explicit_memory_backend_is_still_announced(self, monkeypatch, capsys):
        monkeypatch.setenv(STORE_BACKEND_ENV, "memory")

        default_store()

        assert "forget" in capsys.readouterr().err

    def test_an_unknown_backend_is_a_startup_failure_not_a_fallback(self, monkeypatch):
        monkeypatch.setenv(STORE_BACKEND_ENV, "postgres")

        with pytest.raises(StoreMisconfigured) as caught:
            default_store()

        assert "postgres" in str(caught.value)

    def test_choosing_firestore_reaches_for_the_sdk_rather_than_degrading(self, monkeypatch):
        """The SDK is not installed in this suite, by design (pyproject.toml).

        A backend that fell back to memory here would turn a missing
        dependency into silent data loss on the deploy.
        """
        monkeypatch.setenv(STORE_BACKEND_ENV, "firestore")

        with pytest.raises(StoreSdkMissing):
            default_store()


class TestDeployedWiring:
    """The module-level ``app`` — the one Cloud Run runs — has ingest on it."""

    def test_the_default_app_accepts_a_batch_signed_with_the_configured_secret(self):
        from deadman.service import app as default_app

        body, signature = _signed_batch(TEST_INGEST_SECRET.encode())

        status, _headers, response = _call(
            default_app,
            EVIDENCE_PATH,
            method="POST",
            body=body,
            **{SIGNATURE_ENVIRON_KEY: signature},
        )

        assert status == "200 OK"
        assert json.loads(response)["stored"] == 1

    def test_the_default_app_refuses_a_batch_signed_with_anything_else(self):
        from deadman.service import app as default_app

        body, signature = _signed_batch(b"not-the-configured-secret")

        status, _headers, _response = _call(
            default_app,
            EVIDENCE_PATH,
            method="POST",
            body=body,
            **{SIGNATURE_ENVIRON_KEY: signature},
        )

        assert status.startswith("401")
