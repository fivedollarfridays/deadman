---
id: DM2.6
title: Scheduled sweeps and scheduled self-check
plan: plan-sprint-2-engage
status: pending
sprint: '2'
depends_on:
- DM2.4
materialized_by: backlog_materializer
priority: P0
complexity: 25
complexity_scale: lane
type: feature
ac_verified: null
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: 6c7356a9ee8859736b6efaa9e8b4d0ba774342db
  started_at: '2026-08-11T20:43:06.869573+00:00'
---

# Scheduled sweeps and scheduled self-check

Nothing in DM1 runs on its own. This task enables Cloud Scheduler on `deadman-20260810`, creates the job, and gives the service a self-check on that cadence whose evidence is durable rather than per-instance, retiring DM1.11's stated cold-start limitation. The scheduled endpoint is authenticated and separate from the public board, because a public endpoint that triggers work is a free denial-of-service. The collector keeps its own local timer deliberately: two independent clocks mean one dying does not silence the other, which is the whole redundancy argument. This task touches live billable cloud infrastructure and is privileged. Deploy follows merge, or the deployed image tag goes stale.

# Acceptance Criteria

- [ ] Cloud Scheduler API enabled on `deadman-20260810` and a job created, with the exact reproducible commands recorded in `infra/scheduler.md`
- [ ] The scheduled endpoint requires authentication and is not the public board endpoint
- [ ] An unauthenticated request to the scheduled endpoint is rejected, asserted by a test
- [ ] The service's own self-check runs on that cadence and writes self-evidence through the DM2.1 store
- [ ] A test proves self-evidence is read from the store rather than from the per-instance filesystem, so it survives a cold start
- [ ] The collector runs on its own local timer independently of Cloud Scheduler, documented so that one dying does not silence the other
- [ ] The scheduler job is verified to have actually fired at least once, evidenced by a stored row rather than by the job's own status
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean
