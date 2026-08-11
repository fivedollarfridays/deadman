"""What "unreachable" means to a collector, distinct from "answered badly".

The spool's whole job (see ``test_collector_run.py``) turns on that
distinction: a service that is up and rejects a batch is a different fact
from a service this collector cannot even reach. ``urlopen`` is monkeypatched
rather than opened for real, the same way the codebase already tests
``EmailTransport`` without a socket (``tests/test_transports.py``) — the
hermetic suite blocks real connects regardless (``tests/conftest.py``), so
this proves the mapping logic rather than the network.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from deadman.collector.transport import TransportError, UrllibTransport


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_a_200_response_returns_its_status(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResponse(200))
    transport = UrllibTransport()

    status = transport.post("https://example.test/evidence", b"{}", {})

    assert status == 200


def test_an_http_error_status_is_returned_not_raised(monkeypatch):
    def _raise(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.test/evidence", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    transport = UrllibTransport()

    status = transport.post("https://example.test/evidence", b"{}", {})

    assert status == 401


def test_a_connection_failure_raises_transport_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    transport = UrllibTransport()

    with pytest.raises(TransportError):
        transport.post("https://example.test/evidence", b"{}", {})


def test_the_request_carries_the_body_and_headers(monkeypatch):
    captured = {}

    def _capture(request, timeout=None):
        captured["body"] = request.data
        captured["headers"] = dict(request.headers)
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        return _FakeResponse(200)

    monkeypatch.setattr(urllib.request, "urlopen", _capture)
    transport = UrllibTransport()

    transport.post("https://example.test/evidence", b'{"rows":[]}', {"X-Signature": "abc"})

    assert captured["body"] == b'{"rows":[]}'
    assert captured["headers"]["X-signature"] == "abc"
    assert captured["url"] == "https://example.test/evidence"
    assert captured["method"] == "POST"
