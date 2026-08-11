"""The collector end to end: sweep, sign, ship, and never drop a batch.

``FakeTransport`` stands in for the network the same way every other DI seam
in this codebase does (``SchedulerClient``, ``RelayClient``...): no real
socket is ever asked to open, and the hermetic block in ``conftest.py``
would catch it if one were. That is what makes the dry-run "zero network
calls" assertion real rather than aspirational — the default
:class:`~deadman.collector.transport.UrllibTransport` is used for the
dry-run tests specifically so a network attempt would trip the suite-wide
socket block, not just a mock's absence of a call.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from deadman.collector.config import CollectorConfig
from deadman.collector.run import Collector, ConfigError, build_collector, main
from deadman.collector.spool import Spool
from deadman.collector.transport import TransportError, UrllibTransport
from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest.auth import SIGNATURE_HEADER, check_signature
from deadman.ingest.wire import loads as wire_loads

COLLECTOR_ID = "kevin-mac"
SECRET = b"a-shared-secret-for-tests"


def _config(tmp_path: Path, **overrides) -> CollectorConfig:
    fields = {
        "collector_id": COLLECTOR_ID,
        "ingest_url": "https://deadman.example.com",
        "probes": (),
        "spool_dir": tmp_path / "spool",
    }
    fields.update(overrides)
    return CollectorConfig(**fields)


class _GoodProbe:
    surface = "host:disk/"
    question = "is there room?"

    def observe(self) -> Evidence:
        return Evidence(
            surface=self.surface,
            observation=Observation.HEALTHY,
            method=Method.LOCAL_ARTIFACT,
            summary="plenty of room",
            source="test",
        )


class _RaisingProbe:
    surface = "cron:morning-brief"
    question = "was a brief sent?"

    def observe(self) -> Evidence:
        raise RuntimeError("the probe's instrument is broken")


class FakeTransport:
    """Records every call; answers with a scripted sequence of outcomes."""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, bytes, dict]] = []

    def post(self, url: str, body: bytes, headers) -> int:
        self.calls.append((url, body, dict(headers)))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ExplodingTransport:
    """Never allowed to be called: a dry run must reach neither this nor
    a real socket."""

    def post(self, url: str, body: bytes, headers) -> int:
        raise AssertionError("dry-run made a network call")


def _fixed_clock(moments: list[datetime]):
    it = iter(moments)

    def clock() -> datetime:
        return next(it)

    return clock


class TestDryRun:
    def test_prints_the_batch_and_never_calls_the_transport(self, tmp_path, capsys):
        config = _config(tmp_path)
        collector = Collector(
            config=config, secret=SECRET, probes=[_GoodProbe()], transport=ExplodingTransport()
        )

        result = collector.run_once(dry_run=True)

        assert result["dry_run"] is True
        assert result["batch"]["collector_id"] == COLLECTOR_ID
        assert result["batch"]["rows"][0]["surface"] == "host:disk/"

    def test_dry_run_makes_zero_network_calls_under_the_real_transport(self, tmp_path):
        """No socket-blocking mock needed here: UrllibTransport is real, and
        the suite-wide hermetic fixture in conftest.py raises if anything
        tries to connect. A pass here means dry-run truly never reaches
        the network layer."""
        config = _config(tmp_path)
        collector = Collector(
            config=config, secret=SECRET, probes=[_GoodProbe()], transport=UrllibTransport()
        )

        collector.run_once(dry_run=True)  # would raise NetworkBlockedError if it dialed out

    def test_cli_dry_run_prints_json_to_stdout(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("DEADMAN_INGEST_SECRET", "cli-test-secret")
        config_path = tmp_path / "collector.json"
        config_path.write_text(
            json.dumps(
                {
                    "collector_id": COLLECTOR_ID,
                    "ingest_url": "https://deadman.example.com",
                    "spool_dir": str(tmp_path / "spool"),
                    "probes": [
                        {
                            "type": "morning_brief",
                            "args": {"log_path": str(tmp_path / "brief.jsonl")},
                        }
                    ],
                }
            )
        )

        code = main(["--config", str(config_path), "--dry-run"])

        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["collector_id"] == COLLECTOR_ID
        assert out["rows"][0]["surface"] == "cron:morning-brief"


class TestProbeIsolation:
    def test_a_raising_probe_does_not_stop_the_others_from_shipping(self, tmp_path):
        config = _config(tmp_path)
        transport = FakeTransport([200])
        collector = Collector(
            config=config,
            secret=SECRET,
            probes=[_GoodProbe(), _RaisingProbe()],
            transport=transport,
        )

        result = collector.run_once(dry_run=False)

        assert result["delivered"] is True
        (call,) = transport.calls
        batch = wire_loads(call[1])
        surfaces = {row.surface: row.observation for row in batch.rows}
        assert surfaces["host:disk/"] == Observation.HEALTHY
        assert surfaces["cron:morning-brief"] == Observation.UNOBSERVABLE


class TestSigningAndWireFormat:
    def test_the_shipped_batch_is_signed_and_carries_the_collector_id(self, tmp_path):
        config = _config(tmp_path)
        transport = FakeTransport([200])
        collector = Collector(
            config=config, secret=SECRET, probes=[_GoodProbe()], transport=transport
        )

        collector.run_once(dry_run=False)

        url, body, headers = transport.calls[0]
        assert url == "https://deadman.example.com/evidence"
        check_signature(body, headers[SIGNATURE_HEADER], SECRET)  # raises AuthError if wrong
        batch = wire_loads(body)
        assert batch.collector_id == COLLECTOR_ID


class TestStoreAndForward:
    def test_an_unreachable_service_spools_rather_than_drops(self, tmp_path):
        config = _config(tmp_path)
        transport = FakeTransport([TransportError("connection refused")])
        collector = Collector(
            config=config, secret=SECRET, probes=[_GoodProbe()], transport=transport
        )

        result = collector.run_once(dry_run=False)

        assert result["delivered"] is False
        spool = Spool(path=config.spool_dir)
        (item,) = spool.pending()
        assert item.rows[0].surface == "host:disk/"

    def test_a_non_200_response_also_spools_rather_than_drops(self, tmp_path):
        config = _config(tmp_path)
        transport = FakeTransport([500])
        collector = Collector(
            config=config, secret=SECRET, probes=[_GoodProbe()], transport=transport
        )

        collector.run_once(dry_run=False)

        spool = Spool(path=config.spool_dir)
        assert len(spool.pending()) == 1

    def test_a_later_successful_run_drains_the_spooled_batch(self, tmp_path):
        config = _config(tmp_path)
        failing = Collector(
            config=config,
            secret=SECRET,
            probes=[_GoodProbe()],
            transport=FakeTransport([TransportError("down")]),
        )
        failing.run_once(dry_run=False)
        assert len(Spool(path=config.spool_dir).pending()) == 1

        recovering_transport = FakeTransport([200, 200])  # drain, then the new sweep
        recovering = Collector(
            config=config, secret=SECRET, probes=[_GoodProbe()], transport=recovering_transport
        )

        result = recovering.run_once(dry_run=False)

        assert result["drained"] == 1
        assert Spool(path=config.spool_dir).pending() == []
        drained_batch = wire_loads(recovering_transport.calls[0][1])
        assert drained_batch.rows[0].surface == "host:disk/"

    def test_the_resent_batch_is_freshly_signed_not_replayed_stale(self, tmp_path):
        """The freshness window in deadman.ingest.auth is 5 minutes. A spool
        that resent the *original* signed_at verbatim would be rejected as
        stale by any real outage longer than that -- exactly backwards for
        a store-and-forward mechanism. Re-signing at send time is what
        makes an honest retry pass freshness on arrival."""
        config = _config(tmp_path)
        old_moment = datetime(2026, 8, 1, tzinfo=timezone.utc)
        new_moment = old_moment + timedelta(hours=6)

        failing = Collector(
            config=config,
            secret=SECRET,
            probes=[_GoodProbe()],
            transport=FakeTransport([TransportError("down")]),
            clock=_fixed_clock([old_moment]),
        )
        failing.run_once(dry_run=False)

        recovering_transport = FakeTransport([200])
        recovering = Collector(
            config=config,
            secret=SECRET,
            probes=[],
            transport=recovering_transport,
            clock=_fixed_clock([new_moment]),
        )
        recovering.run_once(dry_run=False)

        resent_batch = wire_loads(recovering_transport.calls[0][1])
        assert resent_batch.signed_at == new_moment

    def test_spool_survives_restart_via_a_reconstructed_collector(self, tmp_path):
        config = _config(tmp_path)
        crashed = Collector(
            config=config,
            secret=SECRET,
            probes=[_GoodProbe()],
            transport=FakeTransport([TransportError("down")]),
        )
        crashed.run_once(dry_run=False)

        # A brand new Collector, built with no reference to `crashed` at
        # all -- this is what a restarted process actually does.
        restarted_transport = FakeTransport([200])
        restarted = Collector(
            config=config, secret=SECRET, probes=[], transport=restarted_transport
        )

        result = restarted.run_once(dry_run=False)

        assert result["drained"] == 1
        assert Spool(path=config.spool_dir).pending() == []


class TestStartupFailures:
    def test_a_malformed_config_fails_loudly_naming_the_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEADMAN_INGEST_SECRET", "cli-test-secret")
        config_path = tmp_path / "collector.json"
        config_path.write_text(json.dumps({"ingest_url": "https://x.test", "probes": []}))

        with pytest.raises(ConfigError, match="collector_id"):
            build_collector(config_path)

    def test_the_cli_reports_a_malformed_config_and_exits_non_zero(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setenv("DEADMAN_INGEST_SECRET", "cli-test-secret")
        config_path = tmp_path / "collector.json"
        config_path.write_text(json.dumps({"ingest_url": "https://x.test", "probes": []}))

        code = main(["--config", str(config_path)])

        assert code != 0
        assert "collector_id" in capsys.readouterr().err

    def test_missing_ingest_secret_also_fails_loudly(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("DEADMAN_INGEST_SECRET", raising=False)
        config_path = tmp_path / "collector.json"
        config_path.write_text(
            json.dumps(
                {
                    "collector_id": COLLECTOR_ID,
                    "ingest_url": "https://x.test",
                    "probes": [{"type": "morning_brief", "args": {"log_path": "/tmp/x.jsonl"}}],
                }
            )
        )

        code = main(["--config", str(config_path)])

        assert code != 0
        assert "DEADMAN_INGEST_SECRET" in capsys.readouterr().err


class TestBuildCollector:
    def test_builds_a_working_collector_from_a_real_config_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEADMAN_INGEST_SECRET", "cli-test-secret")
        config_path = tmp_path / "collector.json"
        config_path.write_text(
            json.dumps(
                {
                    "collector_id": COLLECTOR_ID,
                    "ingest_url": "https://x.test",
                    "spool_dir": str(tmp_path / "spool"),
                    "probes": [
                        {
                            "type": "morning_brief",
                            "args": {"log_path": str(tmp_path / "brief.jsonl")},
                        }
                    ],
                }
            )
        )

        collector = build_collector(config_path)

        assert collector.config.collector_id == COLLECTOR_ID
        assert len(collector.probes) == 1
