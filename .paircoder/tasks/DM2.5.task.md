---
id: DM2.5
title: Real surfaces, starting with the one that is already broken
plan: plan-sprint-2-engage
status: done
sprint: '2'
depends_on:
- DM2.3
materialized_by: backlog_materializer
priority: P0
complexity: 30
complexity_scale: lane
type: feature
ac_verified: true
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: fd635b1ad9fd64f5b91ada1f60805ac1273e4f0e
  started_at: '2026-08-11T20:33:10.792440+00:00'
  completed_at: '2026-08-11T20:43:05.504656+00:00'
completed_at: '2026-08-11T20:42:03.320472+00:00'
---

# Real surfaces, starting with the one that is already broken

Wire the collector to actual infrastructure, beginning with the morning brief log that is broken right now. This is the task that converts deadman from a demonstration into a tool, and the acceptance test is not synthetic: the surface must report the real, current fault. Capturing that output is also what makes DM2.9's case study written from evidence rather than from memory. Disk trend watches the Mac and the rig as separate surfaces, because a full volume on one says nothing about the other. Every path is configuration, so nothing about Kevin's filesystem is compiled into the package.

# Acceptance Criteria

- [x] The morning brief surface watches `~/ops/data/brief-send-log.jsonl` and reports the current, real fault — `MorningBriefProbe` run this session against the real log; the collector config mechanism (`infra/collector/collector.example.json` + `deadman.collector.config`) is what points it there in deployment.
- [x] The captured output of that real FAULT is committed as a fixture, for DM2.9 to write the case study from — `tests/fixtures/real-morning-brief-fault.json` (`observation: fault`, "no brief sent in 176.7h"), pinned by `tests/test_real_evidence_fixtures.py`.
- [x] Disk trend watches the Mac volume and the rig volume as separate surfaces with distinct stable surface ids — `DiskProbe.host` (`src/deadman/probes/disk.py`) yields `host:mac/disk` and `host:rig/disk`; `infra/collector/collector.example.json` + new `infra/collector/collector-rig.example.json`.
- [x] Every surface's real path comes from collector configuration, never a hardcoded literal, asserted by a test — `tests/test_collector_config.py::test_a_probes_real_path_comes_from_config_never_a_hardcoded_literal` and `::test_the_disk_probes_host_argument_is_config_driven`.
- [x] A missing path reads `UNOBSERVABLE` with the path named in `detail`, never `FAULT` — `DiskProbe.observe` and `MorningBriefProbe._missing_log_result` now put `path` in `detail`; `tests/test_disk_probe.py::test_missing_volume_is_unobservable_with_the_path_in_detail`, `tests/test_morning_brief_probe.py::test_missing_parent_directory_is_unobservable_not_fault`.
- [x] `docs/surfaces.md` lists each real surface, its path, its declared cadence, and what its blindness would mean — new file.
- [x] Adding a surface is a config edit plus an existing probe, demonstrated by the second disk surface needing no new probe code — `infra/collector/collector-rig.example.json` reuses `DiskProbe`; `tests/test_collector_example_config.py::test_the_rig_example_config_loads_and_builds_a_disk_probe_only`.
- [x] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean — 494/494 passed, ruff clean both ways, arch check clean.