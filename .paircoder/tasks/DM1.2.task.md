---
id: DM1.2
title: Tests for the evidence model and probe contract
plan: plan-sprint-1-engage
status: done
sprint: '1'
depends_on:
- DM1.1
materialized_by: backlog_materializer
priority: P0
complexity: 20
complexity_scale: lane
type: feature
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: b9df4fc9b7b60006c88f36865903cfc3ce7e96dd
  started_at: '2026-08-11T01:10:39.845286+00:00'
  completed_at: '2026-08-11T01:14:20.606343+00:00'
completed_at: '2026-08-11T01:13:17.926934+00:00'
ac_verified: true
---

# Tests for the evidence model and probe contract

Lock the two ideas the whole system rests on. Absence is a distinct state from failure, and evidence carries how it was obtained. These tests are the guardrail against the failure mode already observed in a sibling project, where a swallowed HTTP error surfaced as a data verdict.

# Acceptance Criteria

- [x] A probe that raises yields `Observation.UNOBSERVABLE`, never `FAULT`
- [x] A probe returning a non-`Evidence` value is contained and yields `UNOBSERVABLE`
- [x] `blind_spots()` returns unobserved surfaces and excludes healthy ones
- [x] `Method` trust ordering asserts `DESTINATION_API` outranks `REPORTED`
- [x] `Evidence.provenance_row()` returns source, method, surface, and an ISO timestamp
- [x] `unobservable()` records the reason in `detail`
- [x] `ruff check` clean on touched files