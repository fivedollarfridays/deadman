"""The service's link preview, and the proof that it moved nothing else.

The JSON half is the load-bearing half. The ops board watcher reads ``GET /``
with ``urllib`` and no ``Accept`` header; people read it with ``curl``. For
each of those request shapes the body must equal the board serialised
exactly as it was before the preview existed, and the headers must be the
same two headers, in the same order, with nothing added.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from deadman.evidence.model import Evidence, Method, Observation
from deadman.preview import CARD_PATH, card_bytes
from deadman.service import build_board, make_app

_READ_AT = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
_LINKEDIN = "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)"


class _Probe:
    def __init__(self, surface: str, observation: Observation) -> None:
        self.surface = surface
        self.question = "is it fine?"
        self._evidence = Evidence(
            surface=surface,
            observation=observation,
            method=Method.LOCAL_ARTIFACT,
            summary=f"{surface}: {observation.value}",
            source="test",
            read_at=_READ_AT,
        )

    def observe(self) -> Evidence:
        return self._evidence


class _Log:
    def __init__(self) -> None:
        self.records = 0

    def record(self, *, sweep_size: int, blind: int, when: datetime | None = None) -> None:
        self.records += 1


def _probes() -> list[_Probe]:
    return [_Probe("host:disk", Observation.HEALTHY), _Probe("cron:brief", Observation.FAULT)]


def _call(app, path: str = "/", method: str = "GET", **headers: str):
    captured: dict[str, object] = {}

    def start_response(status: str, response_headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = response_headers

    environ: dict[str, object] = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "wsgi.url_scheme": "http",
        "HTTP_HOST": "board.example.test",
        **headers,
    }
    body = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], body


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"HTTP_USER_AGENT": "curl/8.7.1", "HTTP_ACCEPT": "*/*"},
        {"HTTP_USER_AGENT": "Python-urllib/3.11"},
        {"HTTP_ACCEPT": "application/json"},
        {"HTTP_ACCEPT": "text/html", "QUERY_STRING": "format=json"},
    ],
)
def test_json_clients_get_exactly_the_board_they_always_got(headers: dict[str, str]) -> None:
    expected = json.dumps(build_board(_probes())).encode("utf-8")

    status, response_headers, body = _call(make_app(_probes), **headers)

    assert status == "200 OK"
    assert body == expected
    assert response_headers == [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(expected))),
    ]


@pytest.mark.parametrize(
    "headers",
    [{"HTTP_USER_AGENT": _LINKEDIN}, {"HTTP_ACCEPT": "text/html"}],
)
def test_unfurlers_and_browsers_get_the_preview_page(headers: dict[str, str]) -> None:
    status, response_headers, body = _call(make_app(_probes), **headers)

    page = body.decode("utf-8")
    assert status == "200 OK"
    assert dict(response_headers)["Content-Type"] == "text/html; charset=utf-8"
    assert '<meta property="og:url" content="http://board.example.test/">' in page
    assert f'<meta property="og:image" content="http://board.example.test{CARD_PATH}">' in page
    assert '<meta name="twitter:card" content="summary_large_image">' in page
    assert "cron:brief" in page


def test_the_preview_page_is_a_served_board_and_records_a_sweep() -> None:
    log = _Log()
    _call(make_app(_probes, self_log=log), HTTP_USER_AGENT=_LINKEDIN)
    assert log.records == 1


def test_the_card_is_served_as_a_png_without_running_a_sweep() -> None:
    log = _Log()

    def no_probes() -> list[_Probe]:
        raise AssertionError("serving the card must not sweep")

    status, headers, body = _call(make_app(no_probes, self_log=log), path=CARD_PATH)

    assert status == "200 OK"
    assert dict(headers)["Content-Type"] == "image/png"
    assert dict(headers)["Content-Length"] == str(len(card_bytes()))
    assert body == card_bytes()
    assert log.records == 0


def test_head_of_the_card_sends_headers_and_no_body() -> None:
    status, headers, body = _call(make_app(_probes), path=CARD_PATH, method="HEAD")

    assert status == "200 OK"
    assert dict(headers)["Content-Type"] == "image/png"
    assert body == b""


def test_writing_to_the_card_path_is_refused() -> None:
    status, _, _ = _call(make_app(_probes), path=CARD_PATH, method="POST")
    assert status == "405 Method Not Allowed"
