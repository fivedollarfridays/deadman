---
id: DM3.7
title: Out-of-band check compares transport identity, not the surface-id prefix
plan: plan-2026-09-dm3-5-audit-four-faults
type: bugfix
priority: P0
complexity: 3
status: done
sprint: null
tags: []
depends_on: []
complexity_scale: points
runtime:
  pre_task_sha:
    deadman-faults: dbfbea036ef0da89f4d9044289a2a188b57b76d8
  conflicts_encountered: none
completed_at: '2026-09-27T17:01:18.693436+00:00'
---

# Objective

The out-of-band check compares the alarm's real transport identity (SMTP
account on a host) with the transports monitored surfaces declare, not the
surface-id prefix. Audit finding D3.

# Implementation Plan

1. RED: two differently named surfaces sharing one SMTP account refuse at
   construction, through the production path (`default_alarm` from env and the
   collector declaration).
2. GREEN: `EmailTransport.identity`; an optional `transports` map in the
   collector declaration; `AlertChannel` compares identities.
3. The refusal propagates at startup rather than degrading to "unconfigured".

# Acceptance Criteria

- [x] An alarm on the same SMTP account as a declared monitored surface raises `AlertChannelInvalid` at construction, whatever either is named
- [x] A different account on the same labels constructs
- [x] `default_alarm` lets the refusal propagate
- [x] Production config is not changed; whether it passes is reported

# Verification

- Full suite green; ruff check, ruff format --check, arch check --strict clean