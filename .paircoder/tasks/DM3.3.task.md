---
id: DM3.3
title: Stage 1 alarms on the fault, not on the model's grounding
plan: plan-2026-09-dm3-3-demo-stage1-alarm
type: bugfix
priority: P1
complexity: 2
status: done
sprint: null
tags: []
depends_on: []
complexity_scale: points
runtime:
  pre_task_sha:
    deadman-demo-fix: caf27687a2bc057fc217ff1616ef1bd00c673aa1
  conflicts_encountered: none
completed_at: '2026-09-25T20:19:40.188465+00:00'
---

# Objective

A detected FAULT on the real surface raises exactly one out-of-band alarm,
whatever the model said about it. The demo never crashes on an empty alert list.

# Context — how this was found

`python scripts/demo.py --live` crashed at stage 1 twice on 2026-09-25 (rig
checkout at 89d206c):

```
  cause      : unknown -> not_attempted
IndexError: tuple index out of range   (scripts/demo.py:103, run.alerts[0])
```

## Root cause

`scripts/demo_real_surface.run_segment` (introduced in c913c96, #15) sends its
alarm only inside `for attempt in outcome.attempts`. `verify_remediation`
returns `NOT_ATTEMPTED` with `attempts=()` when the diagnosis is not actionable
(the ungrounded-diagnosis guard from ef40500, DM1.12, documented and tested).
Live Gemini returns an uncited answer on roughly one run in four
(docs/DEMO.md), so on those runs a real FAULT produced zero alarms.

Not a DM3 regression: #25 touched only `json_heartbeat.py`, which the morning
brief probe does not use. The shipped alarm path
(`deadman.scheduled.alerting.evaluate`) alarms on every FAULT regardless of
diagnosis, so production is unaffected; the demo segment had coupled the alarm
to the model's grounding, which the product never does.

# Implementation Plan

1. RED: `run_segment` with a client whose answer cites nothing yields
   UNGROUNDED, NOT_ATTEMPTED, and still exactly one alarm naming the surface.
2. RED: the alarm carries the executor's refusal reason (ungrounded).
3. RED: demo stage 1 with zero alerts prints a loud failure line and returns
   False instead of raising IndexError.
4. GREEN: alarm on the detected FAULT, with the reason from `executor.plan`;
   demo stage 1 guards the empty list.

# Acceptance Criteria

- [x] An ungrounded diagnosis on a real FAULT still produces exactly one alarm naming `cron:morning-brief`
- [x] The alarm states why nothing was automated (the executor's refusal reason)
- [x] Grounded path unchanged: still exactly one alarm
- [x] Demo stage 1 never raises on an empty alert list; it prints a clear failure and the stage fails
- [x] `python scripts/demo.py --no-pause` (stub) completes all nine stages

# Verification

- Full suite green; ruff check and ruff format --check clean; touched files under 400 lines
- `python scripts/demo.py --no-pause` prints DEMO COMPLETE