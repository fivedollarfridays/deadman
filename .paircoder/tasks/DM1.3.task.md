---
id: DM1.3
title: Tests for the morning brief and disk probes
plan: plan-sprint-1-engage
status: done
sprint: '1'
depends_on:
- DM1.1
materialized_by: backlog_materializer
priority: P0
complexity: 20
complexity_scale: lane
type: feature
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: 51a9ea19da617bb61102e79b3f5a1b5fcd629a0d
  started_at: '2026-08-11T01:14:23.321025+00:00'
  completed_at: '2026-08-11T01:17:33.777051+00:00'
completed_at: '2026-08-11T01:17:04.495828+00:00'
ac_verified: true
---

# Tests for the morning brief and disk probes

Cover the two probes already written, with emphasis on the distinctions that make them correct rather than merely working. The brief probe must never trust file mtime, and the disk probe must fire on a healthy level with a bad trend.

# Acceptance Criteria

- [x] Brief probe: missing log inside an existing directory yields `FAULT` — `tests/test_morning_brief_probe.py::test_missing_log_inside_existing_directory_is_fault`
- [x] Brief probe: missing parent directory yields `UNOBSERVABLE`, not `FAULT` — `tests/test_morning_brief_probe.py::test_missing_parent_directory_is_unobservable_not_fault`
- [x] Brief probe: a file whose mtime is fresh but whose last row is stale still yields `FAULT` — `tests/test_morning_brief_probe.py::test_fresh_mtime_with_stale_last_row_is_still_fault`
- [x] Brief probe: a torn final row falls back to the newest parseable row — `tests/test_morning_brief_probe.py::test_torn_final_row_falls_back_to_newest_parseable_row`
- [x] Brief probe: a future-dated timestamp yields `UNOBSERVABLE` — `tests/test_morning_brief_probe.py::test_future_dated_timestamp_is_unobservable`
- [x] Disk probe: ample free space with a shrinking slope inside the runway window yields `FAULT` — `tests/test_disk_probe.py::test_ample_free_space_with_shrinking_slope_inside_runway_is_fault`
- [x] Disk probe: a single sample yields `HEALTHY` and reports no trend — `tests/test_disk_probe.py::test_single_sample_is_healthy_with_no_trend`
- [x] Disk probe: one outlier sample does not flip the projection — `tests/test_disk_probe.py::test_one_outlier_sample_does_not_flip_the_projection`
- [x] `ruff check` clean on touched files — `ruff check .` → "All checks passed!"