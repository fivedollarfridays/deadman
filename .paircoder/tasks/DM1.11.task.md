---
id: DM1.11
title: Self-liveness and out-of-band alerting
plan: plan-sprint-1-engage
status: in_progress
sprint: '1'
depends_on:
- DM1.8
materialized_by: manual_from_backlog
priority: P1
complexity: 25
complexity_scale: lane
type: feature
model: claude-sonnet-5
base_branch: main
ac_verified: null
---

# Self-liveness and out-of-band alerting

The monitor must prove its own liveness from capture evidence it wrote, and its
alarms must not travel through anything it watches. A sibling system ran dead
for nine days precisely because the failing surface was also the alerting
channel.

# Acceptance Criteria

- [x] `self_check` exits non-zero when the newest self-written evidence is older than the window — verified as a real process, not a return value: `deadman-self-check --log stale.jsonl` prints `stale: last completed sweep was 100.0h ago, outside the 30h window` and exits 1. A `[project.scripts]` console entry point exists so "exits non-zero" is a property of a command a scheduler runs.
- [x] `self_check` exits non-zero when there is no self-written evidence at all — `deadman-self-check --log absent.jsonl` exits 1 with `no_evidence`. `NO_EVIDENCE` is a distinct state from `STALE`, because "it stopped" and "it never started, or we are looking in the wrong place" need different responses.
- [x] Alert transport is asserted at configuration time to not be a monitored surface — `AlertChannel.__post_init__` raises `AlertChannelInvalid`. Checked at construction rather than at send time on purpose: when the alert is needed, the channel is as likely to be down as the thing being reported, so a runtime check discovers the problem exactly when it can no longer be acted on.
- [x] A monitored surface configured as the alert channel raises at startup — `tests/test_alert_channel.py`. Rejection covers the whole rail, not just the exact id: with `sms:relay` monitored, `sms:backup-number` is also refused, because it is the same physical path with a different destination and it dies at the same moment.
- [x] Tests cover live, stale, and no-evidence cases — 12 in `tests/test_self_check.py`, 6 in `tests/test_self_check_cli.py`, 4 in `tests/test_alert_channel.py`. The mtime-immunity test was mutation-checked: swapping `latest()` for the naive `os.path.getmtime` implementation fails it, so the test has teeth rather than passing by construction.
- [x] `ruff check` clean on touched files — `ruff check .` and `ruff format --check .` clean; full suite 222 passed; `bpsai-pair arch check --strict` clean on both new modules.