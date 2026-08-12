---
id: DM2.7
title: An alarm that actually reaches Kevin
plan: plan-sprint-2-engage
status: blocked
sprint: '2'
depends_on:
- DM2.1
materialized_by: backlog_materializer
priority: P0
complexity: 30
complexity_scale: lane
type: feature
ac_verified: null
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: a6de1524cdda4f23d0ce7667a1e43d0055c51659
  started_at: '2026-08-11T19:46:06.295736+00:00'
  completed_at: '2026-08-11T20:01:17.249883+00:00'
---

# An alarm that actually reaches Kevin

DM1.11 built `AlertChannel` with a startup refusal to sit on a rail deadman watches, but nothing real is wired to it. This task delivers an email transport over the existing ops rail and runs the out-of-band assertion against the real monitored surface list, so misconfiguration is caught at startup rather than at the moment the alarm is needed. Throttling is required because a persistent fault sweeps every cadence, but a throttle that swallows a state change is worse than no throttle: the transition from fault to healthy, or healthy to fault, must always get through. A transport that fails is itself evidence and gets stored rather than swallowed.

# Acceptance Criteria

- [x] An email transport delivers through the existing ops email rail and one real message is confirmed received — **DONE 2026-08-12.** The DUMMY label the build agent read was stale: the rail works, proven behaviorally rather than by reading `.env` (the morning brief delivered through it until 2026-08-04). Two real messages sent and confirmed received in Kevin's inbox via Gmail: one through `ops/lib/email_send.py` directly (04:52Z), and one through **deadman's own `EmailTransport`** via `email_transport_from_env` with the ops `SMTP_*` values mapped to `DEADMAN_ALERT_*` (04:53Z, subject "deadman: DM2.7 verification via deadman's own EmailTransport"). The out-of-band assertion ran against the real monitored surface list (`host:disk/`, `cron:morning-brief`) and construction succeeded, since email is not a monitored rail.
- [x] The out-of-band assertion runs against the real monitored surface list rather than a literal, so wiring the alarm to a watched rail raises at construction — `real_monitored_surfaces()` in `src/deadman/remediate/transports.py` reads `deadman.service.default_probes()` directly rather than a retyped literal.
- [x] A test wires the alarm to a monitored rail and asserts the construction-time refusal — `test_wiring_the_alarm_to_a_real_monitored_rail_raises_at_construction` in `tests/test_transports.py`.
- [x] Repeated identical alerts are throttled by a documented window — `ThrottledAlertChannel` + `DEFAULT_THROTTLE_WINDOW` (1h, documented in `docs/alerting.md`); `test_repeated_identical_state_is_throttled_within_the_window`.
- [x] A state change inside the throttle window is always delivered, asserted by a test that flips state mid-window — `test_a_state_change_inside_the_window_is_always_delivered`; mutation-checked (removing the `state == prior_state` guard fails this test).
- [x] A transport failure is recorded as evidence through the DM2.1 store rather than swallowed — `record_transport_failures()`; `test_a_transport_failure_is_recorded_as_evidence_rather_than_swallowed`; mutation-checked (removing the re-raise fails the test, since the exception no longer propagates).
- [x] `docs/alerting.md` documents the rail, the throttle window, and why the rail is out of band relative to every monitored surface — written, including the blocked-verification finding above rather than a fabricated result.
- [x] Credentials for the rail come from the environment and are absent from the repo — `email_transport_from_env` reads six `DEADMAN_ALERT_*` variables and raises `EmailTransportNotConfigured` if any are missing; `EmailTransport`'s credential fields have no defaults (`test_email_transport_has_no_hardcoded_credential_defaults`).
- [x] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean — 362 passed, ruff clean both ways, arch check clean.