---
id: DM2.7
title: An alarm that actually reaches Kevin
plan: plan-sprint-2-engage
status: pending
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
---

# An alarm that actually reaches Kevin

DM1.11 built `AlertChannel` with a startup refusal to sit on a rail deadman watches, but nothing real is wired to it. This task delivers an email transport over the existing ops rail and runs the out-of-band assertion against the real monitored surface list, so misconfiguration is caught at startup rather than at the moment the alarm is needed. Throttling is required because a persistent fault sweeps every cadence, but a throttle that swallows a state change is worse than no throttle: the transition from fault to healthy, or healthy to fault, must always get through. A transport that fails is itself evidence and gets stored rather than swallowed.

# Acceptance Criteria

- [ ] An email transport delivers through the existing ops email rail and one real message is confirmed received
- [ ] The out-of-band assertion runs against the real monitored surface list rather than a literal, so wiring the alarm to a watched rail raises at construction
- [ ] A test wires the alarm to a monitored rail and asserts the construction-time refusal
- [ ] Repeated identical alerts are throttled by a documented window
- [ ] A state change inside the throttle window is always delivered, asserted by a test that flips state mid-window
- [ ] A transport failure is recorded as evidence through the DM2.1 store rather than swallowed
- [ ] `docs/alerting.md` documents the rail, the throttle window, and why the rail is out of band relative to every monitored surface
- [ ] Credentials for the rail come from the environment and are absent from the repo
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean
