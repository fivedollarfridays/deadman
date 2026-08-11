---
id: DM1.9
title: Phone and SMS relay probe with active canary
plan: plan-sprint-1-engage
status: done
sprint: '1'
depends_on:
- DM1.1
materialized_by: backlog_materializer
priority: P1
complexity: 30
complexity_scale: lane
type: feature
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: b87215348105ab92a7a47b4a5a24a4d0a2344ebe
  started_at: '2026-08-11T01:40:08.064084+00:00'
  completed_at: '2026-08-11T01:45:54.541967+00:00'
completed_at: '2026-08-11T01:44:45.336419+00:00'
ac_verified: true
---

# Phone and SMS relay probe with active canary

The surface where passive observation is genuinely ambiguous. Silence means either no traffic or a dead rail and those look identical, so this probe manufactures its own evidence rather than inferring health from quiet.

# Acceptance Criteria

- [x] Silence without a canary yields `UNOBSERVABLE`, never `HEALTHY` — `observe()`'s cadence-not-due branch in `src/deadman/probes/sms_relay.py` returns `unobservable(...)`, never a verdict; `tests/test_probe_sms_relay.py::test_no_canary_due_yet_is_unobservable_never_healthy`
- [x] The canary send is verified at the destination sent folder, not at dispatch — `_verify_landing` only runs after `DispatchOutcome.ACCEPTED`, and reads `SentFolderReader.find(token)` rather than trusting the dispatch ack; `test_canary_accepted_but_absent_from_sent_folder_is_fault` proves an accepted-but-unlanded canary is `FAULT`, not `HEALTHY`
- [x] An unreachable host is distinguished from a rejected send in the evidence detail — `DispatchOutcome.UNREACHABLE` → `UNOBSERVABLE` with `detail["dispatch_outcome"] == "unreachable"`; `DispatchOutcome.REJECTED` → `FAULT` with `detail["dispatch_outcome"] == "rejected"`; `test_unreachable_relay_host_is_unobservable_never_fault` and `test_rejected_send_is_fault_distinct_from_unreachable`
- [x] Canary cadence is configurable and defaults to conservative — `SmsRelayProbe.cadence_hours` field, `DEFAULT_CADENCE_HOURS = 12.0` (twice a day, real sends against a real carrier); `test_cadence_default_is_conservative`, `test_cadence_is_configurable`
- [x] Tests cover reachable, unreachable, and send-rejected with no live network calls — 14 tests in `tests/test_probe_sms_relay.py`; sockets are blocked suite-wide by `tests/conftest.py`'s autouse fixture (no `allow_network` marker used here)
- [x] `ruff check` clean on touched files — `ruff check src/deadman/probes/sms_relay.py tests/test_probe_sms_relay.py` → `All checks passed!`; full suite 61/61 passing, `bpsai-pair arch check --strict` clean