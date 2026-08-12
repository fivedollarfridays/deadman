"""The alarm actually fires: the wiring between detection and delivery.

Every component this exercises already existed and was already tested —
``ThrottledAlertChannel``, ``record_transport_failures``, the out-of-band
refusal, ``EmailTransport``. What had never existed is a caller: the deployed
service recorded faults faithfully and told no one, which is the board-as-brief
problem one level up. This suite pins the evaluator that runs on the scheduled
sweep, because a monitor that needs to be asked is not finished.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deadman.evidence.model import Evidence, Method, Observation
from deadman.scheduled.alerting import AlarmUnconfigured, alarm_from_env, evaluate
from deadman.self_check import Liveness
from deadman.store.memory import InMemoryEvidenceStore
from deadman.verify.collector_liveness import CollectorReport, LivenessReport
from deadman.verify.expectations import CollectorExpectation

NOW = datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc)

EXPECTATION = CollectorExpectation(
    collector_id="kevin-mac",
    interval_seconds=900.0,
    surfaces=("host:mac/disk", "cron:morning-brief"),
)


def _row(surface: str, observation: Observation, summary: str = "") -> Evidence:
    return Evidence(
        surface=surface,
        observation=observation,
        method=Method.REPORTED,
        summary=summary or f"{surface} is {observation.value}",
        source="test",
        read_at=NOW,
        detail={},
    )


def _liveness(
    *,
    collectors: tuple[CollectorReport, ...] = (),
    surfaces: tuple[Evidence, ...] = (),
) -> LivenessReport:
    kinds = [e.observation for e in surfaces]
    return LivenessReport(
        collectors=collectors,
        surfaces=surfaces,
        fresh=sum(1 for k in kinds if k is not Observation.UNOBSERVABLE),
        stale=0,
        unreported=0,
        undeclared=(),
    )


class _RecordingChannel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def alert(self, key: str, state: str, message: str, *, now=None) -> None:
        self.calls.append((key, state, message))


class TestWhatFires:
    def test_a_fault_surface_fires(self):
        channel = _RecordingChannel()
        report = _liveness(
            surfaces=(_row("cron:morning-brief", Observation.FAULT, "no brief in 185h"),)
        )

        fired = evaluate(report, local_evidence=[], channel=channel, now=NOW)

        assert [(k, s) for k, s, _ in channel.calls] == [("cron:morning-brief", "fault")]
        assert fired == 1
        assert "no brief in 185h" in channel.calls[0][2]

    def test_a_stale_collector_fires(self):
        """The fire drill's exact case: the collector goes quiet."""
        channel = _RecordingChannel()
        report = _liveness(
            collectors=(
                CollectorReport(
                    expectation=EXPECTATION,
                    liveness=Liveness.STALE,
                    last_report_at=NOW,
                    silent_for_seconds=2400.0,
                    checked_at=NOW,
                ),
            )
        )

        evaluate(report, local_evidence=[], channel=channel, now=NOW)

        assert [(k, s) for k, s, _ in channel.calls] == [("collector:kevin-mac", "stale")]
        assert "kevin-mac" in channel.calls[0][2]

    def test_a_collector_that_never_reported_fires_as_its_own_state(self):
        channel = _RecordingChannel()
        report = _liveness(
            collectors=(
                CollectorReport(
                    expectation=EXPECTATION,
                    liveness=Liveness.NO_EVIDENCE,
                    last_report_at=None,
                    silent_for_seconds=None,
                    checked_at=NOW,
                ),
            )
        )

        evaluate(report, local_evidence=[], channel=channel, now=NOW)

        assert [(k, s) for k, s, _ in channel.calls] == [("collector:kevin-mac", "no_evidence")]

    def test_a_stale_surface_fires(self):
        """A surface judged unobservable by staleness is a blind spot growing;
        silence about it is how the estate goes dark one surface at a time."""
        channel = _RecordingChannel()
        report = _liveness(
            surfaces=(_row("host:mac/disk", Observation.UNOBSERVABLE, "stale for 3600s"),)
        )

        evaluate(report, local_evidence=[], channel=channel, now=NOW)

        assert [(k, s) for k, s, _ in channel.calls] == [("host:mac/disk", "unobservable")]

    def test_a_local_probe_fault_fires(self):
        channel = _RecordingChannel()

        evaluate(
            _liveness(),
            local_evidence=[_row("host:disk/", Observation.FAULT, "2 days of runway")],
            channel=channel,
            now=NOW,
        )

        assert [(k, s) for k, s, _ in channel.calls] == [("host:disk/", "fault")]


class TestWhatDoesNotFire:
    def test_healthy_is_silence(self):
        channel = _RecordingChannel()
        report = _liveness(
            collectors=(
                CollectorReport(
                    expectation=EXPECTATION,
                    liveness=Liveness.LIVE,
                    last_report_at=NOW,
                    silent_for_seconds=60.0,
                    checked_at=NOW,
                ),
            ),
            surfaces=(_row("host:mac/disk", Observation.HEALTHY),),
        )

        fired = evaluate(report, local_evidence=[], channel=channel, now=NOW)

        assert channel.calls == []
        assert fired == 0

    def test_a_locally_unobservable_probe_does_not_fire(self):
        """The service's own MorningBriefProbe is permanently blind inside the
        container (no log mounted). That is a declared blind spot on every
        sweep, not a state change; alerting it would page Kevin four times an
        hour forever about topology. The collector-side staleness path is what
        watches the real log."""
        channel = _RecordingChannel()

        evaluate(
            _liveness(),
            local_evidence=[_row("cron:morning-brief", Observation.UNOBSERVABLE)],
            channel=channel,
            now=NOW,
        )

        assert channel.calls == []


class TestConstructionFromEnv:
    _FULL_ENV = {
        "DEADMAN_ALERT_SMTP_HOST": "smtp.example.com",
        "DEADMAN_ALERT_SMTP_PORT": "587",
        "DEADMAN_ALERT_SMTP_USER": "u",
        "DEADMAN_ALERT_SMTP_PASSWORD": "p",
        "DEADMAN_ALERT_FROM": "deadman@example.com",
        "DEADMAN_ALERT_TO": "kevin@example.com",
    }

    def test_unconfigured_raises_rather_than_returning_a_dud(self):
        with pytest.raises(AlarmUnconfigured):
            alarm_from_env(store=InMemoryEvidenceStore(), monitored=["host:mac/disk"], environ={})

    def test_configured_builds_a_throttled_out_of_band_channel(self):
        alarm = alarm_from_env(
            store=InMemoryEvidenceStore(),
            monitored=["host:mac/disk", "cron:morning-brief"],
            environ=dict(self._FULL_ENV),
        )

        assert hasattr(alarm, "alert")

    def test_an_email_monitored_rail_is_refused_at_construction(self):
        """The DM1.11 argument, now enforced at the real construction site:
        if deadman ever watches an email surface, alerting over email dies at
        startup instead of at the moment the alarm is needed."""
        from deadman.remediate.alert import AlertChannelInvalid

        with pytest.raises(AlertChannelInvalid):
            alarm_from_env(
                store=InMemoryEvidenceStore(),
                monitored=["email:some-inbox"],
                environ=dict(self._FULL_ENV),
            )


class TestFailureHandling:
    def test_a_transport_failure_is_recorded_as_evidence_and_propagates(self):
        store = InMemoryEvidenceStore()
        alarm = alarm_from_env(
            store=store,
            monitored=["host:mac/disk"],
            environ=dict(TestConstructionFromEnv._FULL_ENV),
        )
        # No stubbing: the suite's hermetic socket block makes the real SMTP
        # connect raise, which exercises the actual recorded wrapper built at
        # construction rather than a substitute bolted on afterwards.
        report = _liveness(surfaces=(_row("host:mac/disk", Observation.FAULT),))

        with pytest.raises(OSError):
            evaluate(report, local_evidence=[], channel=alarm, now=NOW)

        stored = store.latest("alert:email")
        assert stored is not None
        assert stored.observation is Observation.FAULT
        assert "alert transport failed" in stored.summary


class TestTheEndpointNamesTheAlarmState:
    """The response carries ``alerting`` either way. An unconfigured alarm
    that only warned at boot would scroll away; naming it on every trigger
    puts the gap on the job Cloud Scheduler is already watching."""

    def _endpoint(self, alarm, liveness_fn=None):
        from deadman.scheduled.endpoint import ScheduledSelfCheckEndpoint
        from deadman.self_check import StoreSelfEvidenceLog

        return ScheduledSelfCheckEndpoint(
            probes_fn=lambda: [],
            self_log=StoreSelfEvidenceLog(store=InMemoryEvidenceStore()),
            secret="s",
            alarm=alarm,
            liveness_fn=liveness_fn,
        )

    def _environ(self):
        return {"HTTP_AUTHORIZATION": "Bearer s"}

    def test_unconfigured_is_named_in_the_response(self):
        status, payload = self._endpoint(alarm=None).handle(self._environ())

        assert status.startswith("200")
        assert payload["alerting"] == "unconfigured"

    def test_configured_evaluates_and_reports_the_count(self):
        channel = _RecordingChannel()
        report = _liveness(
            surfaces=(_row("cron:morning-brief", Observation.FAULT, "no brief in 185h"),)
        )

        status, payload = self._endpoint(alarm=channel, liveness_fn=lambda: report).handle(
            self._environ()
        )

        assert status.startswith("200")
        assert payload["alerting"] == "active"
        assert payload["alerts_evaluated"] == 1
        assert [(k, s) for k, s, _ in channel.calls] == [("cron:morning-brief", "fault")]

    def test_self_evidence_is_recorded_before_a_failing_alarm_raises(self):
        """A broken transport must not erase the fact the sweep happened."""
        from deadman.scheduled.endpoint import ScheduledSelfCheckEndpoint
        from deadman.self_check import StoreSelfEvidenceLog

        store = InMemoryEvidenceStore()

        class _Boom:
            def alert(self, key, state, message, *, now=None):
                raise ConnectionError("smtp down")

        endpoint = ScheduledSelfCheckEndpoint(
            probes_fn=lambda: [],
            self_log=StoreSelfEvidenceLog(store=store),
            secret="s",
            alarm=_Boom(),
            liveness_fn=lambda: _liveness(surfaces=(_row("host:mac/disk", Observation.FAULT),)),
        )

        with pytest.raises(ConnectionError):
            endpoint.handle({"HTTP_AUTHORIZATION": "Bearer s"})

        assert store.latest("self:sweep") is not None
