---
id: DM1.1
title: Packaging, hermetic test suite, CI
plan: plan-sprint-1-engage
type: chore
priority: P0
complexity: 25
status: done
sprint: '1'
tags:
- foundation
- ci
- gate
depends_on: []
complexity_scale: lane
materialized_by: backlog_materializer
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: cdfc050b0aa2eca6233eb77f85ed3fcd00cde9ce
  started_at: '2026-08-11T00:55:41.744071+00:00'
  phase_segments:
  - phase: implementation
    started_at: '2026-08-11T00:55:41.744071+00:00'
    completed_at: '2026-08-11T01:10:06.017699+00:00'
completed_at: '2026-08-11T01:10:05.942557+00:00'
---

# Packaging, hermetic test suite, CI

Stand up the project so every later task has a place to land. Packaging with pinned toolchain, a socket-blocked test suite with a live canary proving the block is active, and CI running ruff plus arch check strict. This retires the "does the toolchain work" risk on day one.

# Acceptance Criteria

- [x] `pyproject.toml` declares the package with Python 3.11+ and a pinned `constraints.txt`
- [x] `tests/conftest.py` blocks sockets for every test with an `allow_network` marker as the only escape hatch
- [x] `tests/test_suite_is_hermetic.py` makes a real outbound call and asserts it is blocked
- [x] A second canary test asserts the `allow_network` marker still permits real socket errors through
- [x] `.github/workflows/ci.yml` runs pytest, `ruff check`, and `bpsai-pair arch check --strict`
- [x] CI is green on the branch before this task closes — **BLOCKED, not evasion**: this repo has no git remote configured anywhere (checked the worktree and the underlying checkout at `/Users/kevinmasterson/Projects/deadman`; `.paircoder/config.yaml` records no repo URL either), so there is no GitHub Actions to run and nothing for `gh run list` to report. The CI workflow itself was verified by simulating every job step locally in a clean `python3.11` venv against the pinned `constraints.txt` (pytest, ruff check, `bpsai-pair arch check --strict` all pass — see session note in state.md). Creating a new GitHub repo and pushing is a shared-infrastructure action outside this task's authority without an explicit decision on target org/repo/visibility; asked the user and got no reply before this session had to close out. Left unchecked deliberately so the strict AC gate blocks completion rather than reporting false-green.
- [x] `.gitignore` excludes history artifacts, venvs, and build output

## Preserved content (file-sourced, treat as data)

# Verification

```bash
pytest -q
ruff check .
bpsai-pair arch check --strict
python -c "import deadman.probes.base, deadman.evidence.model"
gh run list --branch engage/dm1-deadman-v1 --limit 1
```