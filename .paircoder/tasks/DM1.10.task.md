---
id: DM1.10
title: Cross-surface correlation
plan: plan-sprint-1-engage
status: done
sprint: '1'
depends_on:
- DM1.3
- DM1.5
materialized_by: backlog_materializer
priority: P1
complexity: 30
complexity_scale: lane
type: feature
model: claude-opus-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: 23d73169b59f866a3e6f42278b3d37795717b68d
  started_at: '2026-08-11T02:15:49.716769+00:00'
  completed_at: '2026-08-11T02:27:21.276709+00:00'
completed_at: '2026-08-11T02:27:00.911216+00:00'
ac_verified: true
---

# Cross-surface correlation

The differentiator against graph-based monitoring. No lineage graph exists across a disk, a phone relay and a scheduler, so a shared root cause must be inferred from co-occurrence and evidence rather than traversed. Inferring the graph is harder than walking a given one.

# Acceptance Criteria

- [x] Concurrent faults across surfaces are offered as one incident with a hypothesised shared cause
- [x] The report states the relationship was inferred, not traversed
- [x] A single isolated fault never produces a correlation
- [x] Correlation confidence is carried and surfaced, never implied
- [x] Tests cover the disk-fills-then-everything-dies case using recorded evidence
- [x] `ruff check` clean on touched files