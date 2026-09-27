---
id: DM3.5
title: Expose the scheduled self-check's age on the board so an independent clock
  can alarm on it
plan: plan-2026-09-dm3-5-audit-four-faults
type: bugfix
priority: P0
complexity: 5
status: done
sprint: null
tags: []
depends_on: []
complexity_scale: points
runtime:
  pre_task_sha:
    deadman-faults: fecdae6b7903342df2865698ce83c8cad019f0b9
  conflicts_encountered: none
completed_at: '2026-09-27T17:01:19.914334+00:00'
---

# Objective

A stopped or broken Cloud Scheduler becomes visible to a watcher on a clock the
service does not own. Audit finding D1 (and C3).

# Context

All alerting runs inside `POST /self-check`, which only Cloud Scheduler calls.
The self-check writes `self:sweep`, but nothing judges it: it lands in
`undeclared_surfaces`, and the only reader is the next trigger, which never
comes if the scheduler stops. The window it would be judged against was 30h
for a 15-minute job.

# Implementation Plan

1. RED through `GET /`: a board served after the scheduler stops reports the
   self-check as stale, with its last-run instant and age.
2. GREEN: a new additive board field `self_check`; no existing field changes.
3. Tighten the scheduled window to a small multiple of the 15-minute interval.
4. Document the contract for the independent watcher; correct infra/scheduler.md.

# Acceptance Criteria

- [x] `GET /` carries a `self_check` object with `liveness`, `last_run_at`, `age_seconds`, `window_seconds`, `interval_seconds`
- [x] The scheduled self-check's staleness window is three scheduler intervals, not 30 hours
- [x] Every pre-existing board field is unchanged (DM1 contract tests green)
- [x] infra/scheduler.md no longer claims `self:sweep` staleness is visible by itself; the watcher contract is documented

# Verification

- Full suite green; ruff check, ruff format --check, arch check --strict clean