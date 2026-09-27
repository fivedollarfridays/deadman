---
id: DM3.7
title: Out-of-band check compares transport identity, not the surface-id prefix
plan: plan-2026-09-dm3-5-audit-four-faults
type: bugfix
priority: P0
complexity: 3
status: pending
sprint: null
tags: []
depends_on: []
complexity_scale: points
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

- [ ] An alarm on the same SMTP account as a declared monitored surface raises `AlertChannelInvalid` at construction, whatever either is named
- [ ] A different account on the same labels constructs
- [ ] `default_alarm` lets the refusal propagate
- [ ] Production config is not changed; whether it passes is reported

# Verification

- Full suite green; ruff check, ruff format --check, arch check --strict clean
