"""Local blindness alarms, except for the one probe named as blind by design.

Audit finding D4: the scheduled alarm fired on a local row only when it was a
FAULT, so every local blind spot was silent. The intent was to exempt one
probe that is blind by topology inside the container, and the constant naming
it, ``_PERMANENTLY_BLIND_LOCAL``, was referenced nowhere. On an edge box, where
the local probes are the cameras, that shape silences every camera outage.

Driven through the scheduled endpoint and the real throttled email channel;
only the SMTP socket is replaced.
"""

from __future__ import annotations

import pytest
from alarm_harness import AUTHORIZED, StaticProbe, install_fake_smtp, production_endpoint

from deadman.evidence.model import Observation
from deadman.scheduled.alerting import _PERMANENTLY_BLIND_LOCAL

NAMED_BLIND = "cron:morning-brief"
UNNAMED_BLIND = "host:disk/"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_fake_smtp(monkeypatch)


def test_the_exemption_names_the_probe_this_suite_treats_as_named():
    assert NAMED_BLIND in _PERMANENTLY_BLIND_LOCAL
    assert UNNAMED_BLIND not in _PERMANENTLY_BLIND_LOCAL


def test_an_unnamed_blind_local_probe_alarms_and_the_named_one_does_not(outbox):
    endpoint = production_endpoint(
        [
            StaticProbe(NAMED_BLIND, Observation.UNOBSERVABLE),
            StaticProbe(UNNAMED_BLIND, Observation.UNOBSERVABLE),
        ]
    )

    status, payload = endpoint.handle(dict(AUTHORIZED))

    assert status.startswith("200")
    assert payload["alerts_evaluated"] == 1
    assert len(outbox) == 1
    assert UNNAMED_BLIND in outbox[0]
    assert "unobservable" in outbox[0]
    assert NAMED_BLIND not in outbox[0]


def test_a_healthy_local_probe_still_sends_nothing(outbox):
    endpoint = production_endpoint([StaticProbe(UNNAMED_BLIND, Observation.HEALTHY)])

    _, payload = endpoint.handle(dict(AUTHORIZED))

    assert payload["alerts_evaluated"] == 0
    assert outbox == []
