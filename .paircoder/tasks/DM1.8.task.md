---
id: DM1.8
title: Cloud Run deployment via Cloud Build
plan: plan-sprint-1-engage
status: blocked
sprint: '1'
depends_on:
- DM1.1
materialized_by: backlog_materializer
priority: P0
complexity: 30
complexity_scale: lane
type: feature
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: 66da8463b2159020e23c2a7624684c72df103299
  started_at: '2026-08-11T01:33:54.096314+00:00'
  completed_at: '2026-08-11T01:40:05.564440+00:00'
ac_verified: null
---

# Cloud Run deployment via Cloud Build

Satisfy the contest requirement for at least one Google Cloud infrastructure service with visible proof it runs there. Build through Cloud Build specifically so no local Docker daemon is required.

# Acceptance Criteria

- [x] `Dockerfile` builds the service image — `docker build -t deadman-dm18-local:test .` succeeded locally; `docker run` + `curl http://localhost:18080/` returned the board as JSON (200) with the container's own disk probe `healthy` and the morning-brief probe correctly `unobservable` (no log mounted). Image removed after verification.
- [x] `cloudbuild.yaml` builds and pushes without a local Docker daemon — steps use `gcr.io/cloud-builders/docker` (Cloud Build's own worker) for build/push and `gcr.io/google.com/cloudsdktool/cloud-sdk` for `gcloud run deploy`; nothing in the pipeline touches a local daemon. YAML structure validated with `yaml.safe_load`.
- [x] Service deploys to Cloud Run and returns the current board at a reachable endpoint — live at https://deadman-mrapac5nda-uc.a.run.app (project `deadman-20260810`, region `us-central1`). `GET /` returns HTTP 200 with the board: `host:disk/` healthy, `cron:morning-brief` unobservable, `blind_spots: ["cron:morning-brief"]`, `healthy_count: 1`. Deployed from the rig, which has the gcloud CLI the Mac lacked. Required a fix to `cloudbuild.yaml` (substitutions do not expand inside other substitutions) and a one-time `run.invoker` binding for `allUsers` — without the latter the build reports SUCCESS while every request gets 403 from the Google frontend. Both documented in `infra/README.md`.
- [x] `infra/README.md` documents project setup, required APIs, and the deploy command — `infra/README.md`: prerequisites, API enablement, `gcloud builds submit --config cloudbuild.yaml .`, URL lookup, curl verification, env var config table, optional local-Docker sanity check.
- [x] A fresh clone can reach a deployed URL following only that README — tested by executing the README's commands verbatim against a clean copy, with no substitutions and no undocumented steps: `gcloud builds submit --config cloudbuild.yaml .` (build `91a661d9-e83e-4f6e-81d9-e7dcd02d4196`, SUCCESS, 1m49s), then the documented describe and curl, returning HTTP 200 and the board. The first attempt at this failed on the literal command, which is what surfaced the substitution bug — the README had documented a command nobody had run.
- [x] `ruff check` clean on touched files — `ruff check .` — All checks passed (also `pytest tests/` 47/47, `bpsai-pair arch check --strict` clean).