"""Canary tests proving the hermetic-suite block in ``conftest.py`` is live.

Both tests exercise the real socket layer rather than mocking it, because a
mocked canary can pass while the actual block is disabled.
"""

from __future__ import annotations

import socket

import pytest
from conftest import NetworkBlockedError


def test_outbound_call_is_blocked() -> None:
    """A real outbound connection attempt is intercepted, never reaches the wire."""
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("8.8.8.8", 53), timeout=2)


@pytest.mark.allow_network
def test_allow_network_marker_permits_real_socket_errors() -> None:
    """Under the marker, the real connect() runs and can fail its own way.

    Loopback port 1 is essentially never listening, so this fails fast and
    deterministically with a genuine OS-level error — proof the marker
    restored the real ``socket.connect`` rather than just swallowing the
    block silently.
    """
    with pytest.raises(OSError) as exc_info:
        socket.create_connection(("127.0.0.1", 1), timeout=2)
    assert not isinstance(exc_info.value, NetworkBlockedError)
