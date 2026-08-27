---
id: DM3.1
title: Heartbeat extras must not shadow Evidence field names
plan: plan-2026-08-dm3-probe-detail-collision
type: bugfix
priority: P1
complexity: 2
status: in_progress
sprint: null
tags: []
depends_on: []
complexity_scale: points
runtime:
  pre_task_sha:
    deadman: 2f3fdef73aab007bdd2dc1bcba977a05f5783b71
---

# Objective

A producer's heartbeat JSON must never be able to crash the probe that reads it.

# Context — how this was found

Live, from the alert path doing its job. `cron:devpost` alerted five times on
2026-08-27 (07:00, 08:15, 09:15, 10:15, 11:30) with:

```
cron:devpost is unobservable — cannot observe cron:devpost:
probe raised TypeError: JsonHeartbeatProbe._fault() got multiple values
for argument 'source'
```

## Root cause

`JsonHeartbeatProbe._fault(self, summary: str, source: str, **detail)` takes
`source` positionally. Both call sites pass it positionally **and** splat
`**detail`:

```python
return self._fault(f"no successful run in {age_h:.1f}h (...)", src, **detail)
```

`detail` is seeded with `age_hours` / `window_hours` and then
`detail.update(_bounded_extras(record, exclude=self.timestamp_key))` — and
`_bounded_extras` copies **arbitrary keys straight out of the heartbeat JSON**.
Its `exclude` is a single string (the timestamp key), so it protects
`last_success` and nothing else. **Nothing stops a producer's key from colliding
with a parameter name.**

The devpost heartbeat is `{"last_success", "row", "source"}`. Its `source` key
collides. Any producer that adds one is affected.

## Why it matters more than a crash

The probe was reporting a **real** problem: devpost is genuinely stale
(last_success 2026-08-26T04:42, ~2,126 min against a 1,560 min cap). It tried to
emit `FAULT` and raised on the way, so the board shows `UNOBSERVABLE`.

Those are opposite diagnoses. **UNOBSERVABLE means "we cannot see it" — our
problem. FAULT means "the thing is broken" — theirs.** The bug inverts the
diagnosis on exactly the surfaces that have gone wrong, which is when a monitor
is load-bearing.

**Blast radius:** every local surface uses `JsonHeartbeatProbe` —
`cron:gcal-sync`, `cron:comms-freshness`, `service:staging-queue`,
`cron:kai-cadence`, `cron:devpost`, `cron:digest-hackfw/-tmb/-fwdao`,
`cron:door`. Today only devpost carries a `source` key, so the rest are safe by
luck, not by construction. The healthy path never touches `**detail`, so this
bug is invisible until a surface actually fails.

# Implementation Plan

1. RED: test proving a heartbeat with a `source` key raises today.
2. RED: test proving the same heartbeat should yield `Observation.FAULT`.
3. GREEN: make `_bounded_extras` refuse reserved Evidence field names —
   `surface`, `observation`, `method`, `summary`, `source`, `detail` — in
   addition to the timestamp key. Namespace or drop them; do not silently
   discard without a trace, per the drift doctrine (§5: log skips, never
   silently drop).
4. Confirm the fix at the boundary rather than only the unit: run the real
   devpost heartbeat through the probe and assert FAULT.

# Acceptance Criteria

- [x] A heartbeat containing `source` produces `Observation.FAULT`, not a TypeError
- [x] The same holds for every other Evidence field name (`surface`, `observation`, `method`, `summary`, `detail`) — table-driven, not one case
- [x] The colliding key is still visible in the evidence detail (renamed/namespaced), not silently dropped
- [x] The real `data/devpost-heartbeat.json` payload is exercised as a fixture, not a synthetic stand-in
- [x] Existing `test_probe_json_heartbeat.py` cases stay green
- [x] Healthy path unchanged — no new keys in a healthy Evidence

# Verification

- `PYTHONPATH=src pytest tests/test_probe_json_heartbeat.py -q` green
- Full suite green
- Post-deploy: `cron:devpost` reads **fault** on the board (not `unobservable`),
  with the staleness in its summary
- The alert that follows names a stale rail, not a stack trace