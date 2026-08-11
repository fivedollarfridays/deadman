"""Tests for the Cloud Run service: the board it publishes.

No sockets: ``app`` is a plain WSGI callable, exercised in-process with a
fake ``environ``/``start_response`` pair, exactly like a real WSGI server
would call it, but with nothing bound to a port.
"""

from __future__ import annotations

import json

from deadman.evidence.model import Evidence, Method, Observation
from deadman.service import build_board, make_app


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


def _call(app, path: str = "/", method: str = "GET"):
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    environ = {"PATH_INFO": path, "REQUEST_METHOD": method}
    body = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], body


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
