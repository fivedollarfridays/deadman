---
id: DM1.7
title: Verification loop
plan: plan-sprint-1-engage
status: done
sprint: '1'
depends_on:
- DM1.6
materialized_by: backlog_materializer
priority: P0
complexity: 25
complexity_scale: lane
type: feature
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: 0f164bd0c9e740becfde81621b44b87d6b34509f
  started_at: '2026-08-11T02:27:25.542423+00:00'
  completed_at: '2026-08-11T02:33:28.172834+00:00'
completed_at: '2026-08-11T02:32:24.451864+00:00'
ac_verified: true
---

# Verification loop

Closes the honesty gap. A remediation that reports success without re-observing the surface is just another heartbeat, which is the thing this project argues against. Success means a fresh healthy observation, not an executor return value.

# Acceptance Criteria

- [x] The originating probe is re-run after remediation — `verify_remediation`
      calls `run_probe(probe)` after every `ACT` execution;
      `test_a_verified_fix_re_runs_the_probe_and_requires_healthy` asserts
      `probe.calls == 1`. The probe must be one of the surfaces the diagnosis
      actually cited (`_surfaces(diagnosis)`), enforced by
      `test_verifying_against_an_unrelated_surface_is_refused` — mutation-killed
      by removing the check (probe called against an unrelated surface, no
      `ValueError`).
- [x] Success requires a fresh `HEALTHY` observation from that probe — the sole
      success condition is `reobservation.observation is Observation.HEALTHY`
      (`src/deadman/remediate/verify.py`); mutation-killed by disabling the
      check (`test_a_verified_fix_re_runs_the_probe_and_requires_healthy` and
      `test_a_late_success_stops_the_loop_immediately` both fail).
- [x] The executor's own return value is never sufficient to declare success —
      `test_the_executors_own_return_value_is_never_sufficient` runs an action
      that reports `performed=True` on every attempt while the probe stays
      `FAULT`; outcome is never `VERIFIED`.
- [x] A fix that cannot be re-observed is reported unverified, not successful —
      `test_a_fix_that_cannot_be_reobserved_is_unverified_not_successful`: the
      probe raises, `run_probe` contains it as `UNOBSERVABLE` (never `FAULT`),
      and `outcome.verified is False`.
- [x] Repeated failed remediation stops rather than looping —
      `max_attempts` bounds the loop; `EXHAUSTED` status after the cap
      (`test_repeated_failed_remediation_stops_after_the_attempt_cap`),
      immediate stop on success
      (`test_a_late_success_stops_the_loop_immediately`), `max_attempts < 1`
      rejected (`test_max_attempts_must_be_at_least_one`). Mutation-killed by
      collapsing the loop to always run once.
- [x] `ruff check` clean on touched files — `ruff check src/deadman/remediate/verify.py
      tests/test_remediate_verify.py` → `All checks passed!`; full suite
      `ruff check .` also clean; `pytest tests/` 200/200 (up from 192);
      `bpsai-pair arch check --strict` clean.