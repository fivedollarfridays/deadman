"""Hermetic test suite.

Every test runs with outbound sockets blocked. A probe that quietly reaches
the real network during a test run is exactly the kind of untrustworthy
instrument this project is written against — see
``deadman.probes.base``. The only escape hatch is the ``allow_network``
marker, applied per test, never per file or globally.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator

import pytest

from deadman.ingest.auth import SECRET_ENV
from deadman.scheduled.auth import SECRET_ENV as SCHEDULER_SECRET_ENV

#: The suite's shared ingest secret. :mod:`deadman.service` refuses to import
#: without one (see ``tests/test_ingest_startup.py``, which proves that
#: refusal in a subprocess with this variable stripped), so the suite must
#: supply a value. Set unconditionally rather than with ``setdefault``: a
#: developer with the real secret exported should not have their tests sign
#: batches with it.
TEST_INGEST_SECRET = "test-only-ingest-secret-not-a-real-one"
os.environ[SECRET_ENV] = TEST_INGEST_SECRET

#: Same reasoning, for the scheduled self-check endpoint's shared secret (see
#: ``tests/test_scheduled_startup.py``).
TEST_SCHEDULER_SECRET = "test-only-scheduler-secret-not-a-real-one"
os.environ[SCHEDULER_SECRET_ENV] = TEST_SCHEDULER_SECRET


class NetworkBlockedError(RuntimeError):
    """Raised in place of a real connection attempt during a hermetic test."""


_real_connect = socket.socket.connect


def _blocked_connect(self: socket.socket, address: object) -> None:
    raise NetworkBlockedError(
        f"outbound network access blocked in tests (attempted connect to "
        f"{address!r}); mark the test with @pytest.mark.allow_network to permit it"
    )


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.get_closest_marker("allow_network") is not None:
        yield
        return

    socket.socket.connect = _blocked_connect
    try:
        yield
    finally:
        socket.socket.connect = _real_connect
