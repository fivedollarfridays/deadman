"""Locks the public-path probe's distinguishing behavior.

The class this exists for: a healthy process behind a dead path. The arena
served public 502s under a KeepAlive'd tunnel; the staging queue was
reachable the whole time Kevin was being handed links to a port with no
listener. Process liveness said everything was fine in both cases.

The distinction this probe must never blur: a response we got and disliked
(502, wrong body) is a FAULT — evidence about the surface. A response we
never got (timeout, DNS, refused) is UNOBSERVABLE — evidence about our own
reachability. Confusing the two turns "my wifi dropped" into "the estate is
down", which is the alarm-fatigue path that gets a monitor ignored.
"""

from __future__ import annotations

import pytest

from deadman.evidence.model import Method, Observation
from deadman.probes.base import run_probe
from deadman.probes.public_path import PublicPathProbe

URL = "https://macmini.example.ts.net/brand-index"


class _Resp:
    def __init__(self, status: int, body: bytes = b"ok"):
        self.status = status
        self._body = body

    def read(self, _n: int | None = None) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _probe(**kw):
    defaults = dict(url=URL, surface_id="service:staging-queue")
    defaults.update(kw)
    return PublicPathProbe(**defaults)


def test_200_is_healthy_and_names_the_status():
    ev = _probe(fetch=lambda url, timeout: _Resp(200)).observe()
    assert ev.observation is Observation.HEALTHY
    assert ev.method is Method.DESTINATION_PUBLIC
    assert "200" in ev.summary
    assert ev.detail["status"] == 200
    assert ev.source == URL


def test_502_is_a_fault_not_blindness():
    """The arena class: the front door answered, and what it said was bad."""
    ev = _probe(fetch=lambda url, timeout: _Resp(502)).observe()
    assert ev.observation is Observation.FAULT
    assert "502" in ev.summary


def test_timeout_is_unobservable_not_fault():
    """We learned about our own reachability, not about the surface."""

    def boom(url, timeout):
        raise TimeoutError("timed out")

    ev = _probe(fetch=boom).observe()
    assert ev.observation is Observation.UNOBSERVABLE
    assert not ev.summary.startswith("2")


def test_connection_refused_is_unobservable():
    def boom(url, timeout):
        raise ConnectionRefusedError("refused")

    assert _probe(fetch=boom).observe().observation is Observation.UNOBSERVABLE


def test_200_with_wrong_body_is_a_fault():
    """A parked page, a login wall, or a default nginx index all answer 200.
    A path that resolves to the wrong thing is dead for our purposes."""
    ev = _probe(
        expect_substring="brand",
        fetch=lambda url, timeout: _Resp(200, b"<html>parked domain</html>"),
    ).observe()
    assert ev.observation is Observation.FAULT
    assert "expected content" in ev.summary.lower() or "substring" in ev.summary.lower()


def test_200_with_expected_body_is_healthy():
    ev = _probe(
        expect_substring="brand",
        fetch=lambda url, timeout: _Resp(200, b'{"brand":"tmb"}'),
    ).observe()
    assert ev.observation is Observation.HEALTHY


def test_custom_expected_status_is_respected():
    ev = _probe(expect_status=204, fetch=lambda url, timeout: _Resp(204)).observe()
    assert ev.observation is Observation.HEALTHY


def test_never_raises_under_a_hostile_transport():
    """The never-raise contract: one broken surface must not blind the sweep."""

    def hostile(url, timeout):
        raise RuntimeError("transport exploded in an unexpected way")

    ev = run_probe(_probe(fetch=hostile))
    assert ev.observation is Observation.UNOBSERVABLE


def test_question_names_the_url():
    assert URL in _probe().question


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 500])
def test_non_expected_statuses_are_faults(status):
    ev = _probe(fetch=lambda url, timeout: _Resp(status)).observe()
    assert ev.observation is Observation.FAULT
    assert str(status) in ev.summary
