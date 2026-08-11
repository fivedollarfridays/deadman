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
- [ ] **BLOCKED — cannot verify from this environment.** No `gcloud` CLI, no `~/.config/gcloud`, and no GCP project found anywhere on this machine (checked `PATH`, Homebrew casks, `~/google-cloud-sdk`). Actual `gcloud builds submit` requires credentials this session does not have. See state.md blockers.
- [x] `infra/README.md` documents project setup, required APIs, and the deploy command — `infra/README.md`: prerequisites, API enablement, `gcloud builds submit --config cloudbuild.yaml .`, URL lookup, curl verification, env var config table, optional local-Docker sanity check.
- [ ] **BLOCKED — same as above.** Cannot verify a fresh clone reaches a deployed URL because no URL has been deployed; needs the live deploy step done first.
- [x] `ruff check` clean on touched files — `ruff check .` — All checks passed (also `pytest tests/` 47/47, `bpsai-pair arch check --strict` clean).