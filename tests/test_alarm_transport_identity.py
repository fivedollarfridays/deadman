"""Out of band is decided on the real transport, not on how things are spelled.

Audit finding D3: ``AlertChannel`` compared only the text before the first
colon of each id. The alarm deliberately sends from the same SMTP account the
morning brief uses, but the brief's surface id is ``cron:morning-brief``, so
``email:`` versus ``cron:`` passed. One expired SMTP credential would kill the
brief and its alarm together, and the check could not express it.

The fix: a monitored surface may declare the transport it depends on in the
collector declaration (``transports``), and the alarm's own identity comes
from the SMTP settings it actually sends with. The refusal still happens at
construction, and it propagates out of ``default_alarm`` so the service
refuses to boot rather than degrading to "unconfigured".

Every test goes through ``default_alarm``, the function ``deadman.service``
calls at startup, reading the environment and the declaration file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from alarm_harness import ALERT_ENV

from deadman.remediate.alert import AlertChannelInvalid
from deadman.scheduled.alerting import default_alarm
from deadman.store.memory import InMemoryEvidenceStore
from deadman.verify.expectations import ExpectationError, parse_expectations

#: The alarm's real transport in ``ALERT_ENV``: this SMTP account on this host.
ALARM_IDENTITY = "smtp:smtp.alarm.example/alarm-bot@alarm.example"


def _declare(tmp_path: Path, transports: dict[str, str]) -> Path:
    path = tmp_path / "collectors.json"
    entry = {
        "collector_id": "edge-box",
        "interval_seconds": 900,
        "surfaces": ["cron:morning-brief", "cron:nightly-report"],
        "transports": transports,
    }
    path.write_text(json.dumps({"collectors": [entry]}))
    return path


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def _configure(transports: dict[str, str], **env_overrides: str) -> None:
        for name, value in {**ALERT_ENV, **env_overrides}.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setenv("DEADMAN_COLLECTORS", str(_declare(tmp_path, transports)))

    return _configure


def test_a_differently_named_surface_on_the_alarms_smtp_account_is_refused(configure):
    configure({"cron:morning-brief": ALARM_IDENTITY})

    with pytest.raises(AlertChannelInvalid, match="cron:morning-brief"):
        default_alarm(InMemoryEvidenceStore())


def test_identity_ignores_case_and_surrounding_space(configure):
    configure({"cron:nightly-report": "  SMTP:smtp.ALARM.example/Alarm-Bot@alarm.example "})

    with pytest.raises(AlertChannelInvalid, match="cron:nightly-report"):
        default_alarm(InMemoryEvidenceStore())


def test_a_different_account_on_the_same_labels_constructs(configure):
    configure({"cron:morning-brief": "smtp:smtp.alarm.example/brief-bot@alarm.example"})

    assert default_alarm(InMemoryEvidenceStore()) is not None


def test_a_transport_for_a_surface_the_collector_does_not_report_is_refused():
    entry = {
        "collector_id": "edge-box",
        "interval_seconds": 900,
        "surfaces": ["cron:morning-brief"],
        "transports": {"cron:elsewhere": ALARM_IDENTITY},
    }

    with pytest.raises(ExpectationError, match="transports"):
        parse_expectations({"collectors": [entry]})
