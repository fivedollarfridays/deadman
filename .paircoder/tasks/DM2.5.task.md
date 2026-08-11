---
id: DM2.5
title: Real surfaces, starting with the one that is already broken
plan: plan-sprint-2-engage
status: pending
sprint: '2'
depends_on:
- DM2.3
materialized_by: backlog_materializer
priority: P0
complexity: 30
complexity_scale: lane
type: feature
ac_verified: null
model: claude-sonnet-5
base_branch: main
---

# Real surfaces, starting with the one that is already broken

Wire the collector to actual infrastructure, beginning with the morning brief log that is broken right now. This is the task that converts deadman from a demonstration into a tool, and the acceptance test is not synthetic: the surface must report the real, current fault. Capturing that output is also what makes DM2.9's case study written from evidence rather than from memory. Disk trend watches the Mac and the rig as separate surfaces, because a full volume on one says nothing about the other. Every path is configuration, so nothing about Kevin's filesystem is compiled into the package.

# Acceptance Criteria

- [ ] The morning brief surface watches `~/ops/data/brief-send-log.jsonl` and reports the current, real fault
- [ ] The captured output of that real FAULT is committed as a fixture, for DM2.9 to write the case study from
- [ ] Disk trend watches the Mac volume and the rig volume as separate surfaces with distinct stable surface ids
- [ ] Every surface's real path comes from collector configuration, never a hardcoded literal, asserted by a test
- [ ] A missing path reads `UNOBSERVABLE` with the path named in `detail`, never `FAULT`
- [ ] `docs/surfaces.md` lists each real surface, its path, its declared cadence, and what its blindness would mean
- [ ] Adding a surface is a config edit plus an existing probe, demonstrated by the second disk surface needing no new probe code
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean
