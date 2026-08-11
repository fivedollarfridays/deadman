"""``_read_body`` must not ask the socket for more than the client sent.

Found in production, not in review. The first DM2 deploy answered ``GET /``
fine and then hung on every ``POST /evidence`` until Cloud Run returned 504
after five minutes, with no application log line at all — the request never
finished inside the app.

``_read_body`` called ``stream.read(MAX_BODY_BYTES + 1)`` no matter what the
client declared. Under ``wsgiref.simple_server`` the WSGI input stream is the
raw socket file object and is *not* bounded to ``Content-Length``, so asking
for 256 KiB when the client sent 90 bytes blocks waiting for bytes that will
never come. A collector posting a sweep would hang, which is a monitor whose
only ingest path is broken.

The existing suite could not catch it: it builds ``environ`` with an
``io.BytesIO``, which returns what it has and reports EOF immediately. Every
in-process test passed against a stream that cannot block. So the guard here
is not "did we get the right bytes" — that already passed — but **how many
bytes we asked for**, which is the thing that differs between a BytesIO and a
socket.
"""

from __future__ import annotations

import io

from deadman.ingest.endpoint import MAX_BODY_BYTES, _read_body


class _RecordingStream:
    """A stream that answers reads and remembers what was asked of it.

    Deliberately *not* a socket: reproducing the real block would mean hanging
    the suite. What is asserted instead is the request size, because a read
    bounded by ``Content-Length`` cannot block on a well-behaved client and an
    unbounded one can.
    """

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.requested: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requested.append(size)
        return self.data if size < 0 else self.data[:size]


def _environ(body: bytes, *, declare: bool = True) -> tuple[dict, _RecordingStream]:
    stream = _RecordingStream(body)
    environ: dict = {"wsgi.input": stream}
    if declare:
        environ["CONTENT_LENGTH"] = str(len(body))
    return environ, stream


def test_a_declared_length_bounds_the_read():
    """The regression. Asking for more than was declared is what blocked."""
    body = b'{"version":1}'
    environ, stream = _environ(body)

    assert _read_body(environ) == body
    assert stream.requested == [len(body)], (
        "read must be bounded by Content-Length; asking for MAX_BODY_BYTES+1 "
        "blocks on a real socket until the platform times out"
    )


def test_the_body_still_arrives_intact():
    body = b'{"version":1,"collector_id":"mac-mini","rows":[]}'
    environ, _ = _environ(body)

    assert _read_body(environ) == body


def test_an_undeclared_length_still_reads_up_to_the_cap():
    """No Content-Length means we cannot bound it from the request, so the cap
    is the only bound left — and it is still applied."""
    body = b"{}"
    environ, stream = _environ(body, declare=False)

    assert _read_body(environ) == body
    assert stream.requested == [MAX_BODY_BYTES + 1]


def test_a_declared_length_over_the_cap_is_refused_before_reading():
    """The refusal must not depend on having read the oversized body first."""
    from deadman.ingest.endpoint import BodyTooLarge

    stream = _RecordingStream(b"x")
    environ = {"CONTENT_LENGTH": str(MAX_BODY_BYTES + 1), "wsgi.input": stream}

    try:
        _read_body(environ)
    except BodyTooLarge:
        assert stream.requested == [], "the body must not be read to know it is too large"
    else:  # pragma: no cover - the assertion below reports the failure
        raise AssertionError("an oversized declared length must be refused")


def test_a_bytesio_body_is_unchanged():
    """The shape every other test in the suite uses must keep working."""
    body = b'{"a":1}'
    environ = {"CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}

    assert _read_body(environ) == body
