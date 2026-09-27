---
id: DM3.6
title: A recovery resets the alarm throttle, so a re-fault inside the window alarms
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

A fault that heals and returns inside the throttle window alarms again.
Audit finding D2.

# Context

`evaluate` never tells the throttle about healthy rows, so the throttle still
holds `fault` after a heal and a second fault inside an hour is suppressed as a
repeat. The throttle's "never suppresses a state change" guarantee held only
for callers that send healthy; the production caller does not.

# Implementation Plan

1. RED end to end with a fake clock: fault, heal, fault again at +40 minutes
   through the scheduled endpoint and the real throttled channel.
2. GREEN: `ThrottledAlertChannel.recover` clears the key and sends a recovery
   notice when the key had alerted; `evaluate` calls it for healthy rows.

# Acceptance Criteria

- [ ] A re-fault after a heal inside the throttle window is delivered
- [ ] A heal after an alerted fault sends one recovery notice; a healthy surface that never alerted sends nothing
- [ ] A persisting fault inside the window is still throttled

# Verification

- Full suite green; ruff check, ruff format --check, arch check --strict clean
