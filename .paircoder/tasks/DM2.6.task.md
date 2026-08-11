---
id: DM2.6
title: Scheduled sweeps and scheduled self-check
plan: plan-sprint-2-engage
status: blocked
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

- [ ] Cloud Scheduler API enabled on `deadman-20260810` and a job created, with the exact reproducible commands recorded in `infra/scheduler.md` — **BLOCKED, not done**: `infra/scheduler.md` written with exact, reproducible `gcloud` commands (API enable, secret provisioning, job creation), but this sandboxed worktree has no `gcloud` CLI and no ADC configured (`gcloud`: command not found; `~/.config/gcloud` absent), so the commands have not actually been run against the live project. See "What this document does not close" in `infra/scheduler.md`.
- [x] The scheduled endpoint requires authentication and is not the public board endpoint — `POST /self-check` (`src/deadman/scheduled/endpoint.py`), distinct path from `GET /`, bearer-token auth via `src/deadman/scheduled/auth.py`; `DEADMAN_SCHEDULER_SECRET` is mandatory at import (`tests/test_scheduled_startup.py`), mirroring `DEADMAN_INGEST_SECRET`.
- [x] An unauthenticated request to the scheduled endpoint is rejected, asserted by a test — `tests/test_service_schedule.py::TestUnauthenticatedTriggersAreRejected` (missing header, wrong token, rejected request stores nothing).
- [x] The service's own self-check runs on that cadence and writes self-evidence through the DM2.1 store — `ScheduledSelfCheckEndpoint.handle` sweeps and calls `StoreSelfEvidenceLog.record` (`src/deadman/self_check.py`), wired into `deadman.service.build_app` via `default_scheduled`.
- [x] A test proves self-evidence is read from the store rather than from the per-instance filesystem, so it survives a cold start — `tests/test_service_schedule.py::TestSelfEvidenceSurvivesACleanReadFromAnotherInstance` (two independently-built app instances sharing only a store object) and `tests/test_self_check_store.py::test_a_second_reader_over_the_same_store_sees_what_the_first_wrote`.
- [x] The collector runs on its own local timer independently of Cloud Scheduler, documented so that one dying does not silence the other — already true structurally (`infra/launchd/com.deadman.collector.plist`'s `launchd` timer vs. Cloud Scheduler's HTTP cron are unrelated systems); explained in `infra/scheduler.md`'s "Two independent clocks, on purpose" section.
- [ ] The scheduler job is verified to have actually fired at least once, evidenced by a stored row rather than by the job's own status — **BLOCKED, not done**: verification procedure written in `infra/scheduler.md` (trigger via `gcloud scheduler jobs run`, read back `SELF_CHECK_SURFACE` via `FirestoreEvidenceStore.latest`), but not executable without live `gcloud`/GCP access — same blocker as AC1.
- [x] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean — 528/528 passed, `ruff check .` clean, `ruff format --check .` clean, `arch check --strict` clean.