---
id: DM3.8
title: Only the named permanently-blind local probe is exempt from alarming
plan: plan-2026-09-dm3-5-audit-four-faults
type: bugfix
priority: P0
complexity: 2
status: done
sprint: null
tags: []
depends_on: []
complexity_scale: points
runtime:
  pre_task_sha:
    deadman-faults: c4ed388933420277505d2816649d709183581937
  conflicts_encountered: none
completed_at: '2026-09-27T17:01:07.252232+00:00'
---

# Objective

Only the explicitly named permanently-blind local probe is exempt from the
alarm; every other local blind spot alarms. Audit finding D4.

# Implementation Plan

1. RED through the scheduled endpoint: two blind local probes, one named in
   `_PERMANENTLY_BLIND_LOCAL` and one not; only the unnamed one alarms.
2. GREEN: `evaluate` alarms on local UNOBSERVABLE unless the surface is named.

# Acceptance Criteria

- [x] A blind local probe not named in `_PERMANENTLY_BLIND_LOCAL` alarms
- [x] The named probe does not
- [x] `_PERMANENTLY_BLIND_LOCAL` is the thing that decides

# Verification

- Full suite green; ruff check, ruff format --check, arch check --strict clean