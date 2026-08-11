# Current State

> Last updated: 2026-08-11

<!-- paircoder:state:begin -->
## Active Plan

**Plan:** `plan-2026-08-dm1-deadman-v1` — DM1: deadman v1 (contest-ready)
**Status:** Planned, not started
**Current Sprint:** DM1
**Backlog:** `plans/backlogs/DM1-deadman-v1.md`
**Brief:** `docs/SPRINT-BRIEF-DM1.md`
**Branch:** `engage/dm1-deadman-v1`

Silent-failure detection and remediation for heterogeneous infrastructure.
Submission target: All Things Agentic, Taskmaster category, **deadline
2026-08-31 5:00pm PDT**.

## Current Focus

DM1.1, DM1.2, and DM1.3 are `done`. Remaining wave-2 tasks (DM1.4, DM1.8,
DM1.9) are unblocked and ready to start next.

## Task Status

### Active Sprint (DM1) — 12 tasks, 345 Cx, DM1.1 + DM1.2 + DM1.3 `done`

| ID | Title | Pri | Cx | Model | Depends on |
|---|---|---|---|---|---|
| DM1.1 | Packaging, hermetic test suite, CI ✓ | P0 | 25 | claude-sonnet-5 | — |
| DM1.2 | Evidence model + probe contract tests ✓ | P0 | 20 | claude-sonnet-5 | DM1.1 |
| DM1.3 | Brief + disk probe tests ✓ | P0 | 20 | claude-sonnet-5 | DM1.1 |
| DM1.4 | Metricool probe + verification spike | P1 | 35 | claude-opus-5 | DM1.1 |
| DM1.5 | Diagnosis layer on Gemini via ADK | P0 | 40 | claude-opus-5 | DM1.1, DM1.2 |
| DM1.6 | Remediation registry and executor | P0 | 35 | claude-opus-5 | DM1.5 |
| DM1.7 | Verification loop | P0 | 25 | claude-sonnet-5 | DM1.6 |
| DM1.8 | Cloud Run via Cloud Build | P0 | 30 | claude-sonnet-5 | DM1.1 |
| DM1.9 | SMS relay probe with active canary | P1 | 30 | claude-sonnet-5 | DM1.1 |
| DM1.10 | Cross-surface correlation | P1 | 30 | claude-opus-5 | DM1.3, DM1.5 |
| DM1.11 | Self-liveness + out-of-band alerting | P1 | 25 | claude-sonnet-5 | DM1.8 |
| DM1.12 | Integration gate: demo, README, diagram | P0 | 30 | claude-opus-5 | all |

**Waves:** `DM1.1` → `DM1.2 DM1.3 DM1.4 DM1.8 DM1.9` → `DM1.5 DM1.11` →
`DM1.6 DM1.10` → `DM1.7` → `DM1.12`

**Cut list if over budget, in order:** DM1.10, DM1.9, DM1.11, DM1.4.

### Backlog

Out of scope for DM1 (v2): general surface registry, multi-brand support,
retiring the seven existing point-solution monitors.

## What Was Just Done

### Session: 2026-08-11 — DM1.3 brief + disk probe tests (`/start-task DM1.3`)

- `tests/test_morning_brief_probe.py`: missing log inside an existing
  directory yields `FAULT`; a missing *parent* directory yields
  `UNOBSERVABLE` (config problem, not the brief's fault); a file with a
  fresh mtime but a stale timestamp inside its last row still yields
  `FAULT` (explicitly asserts the mtime *is* fresh, to prove the probe
  isn't using it); a torn final JSONL row falls back to the newest
  parseable row before it (asserted via the fallback row's timestamp and
  `row_count == 2`, not just "didn't error"); a future-dated timestamp
  yields `UNOBSERVABLE` (clock skew, not a verdict).
- `tests/test_disk_probe.py`: mocks `shutil.disk_usage` and pre-seeds
  `DiskProbe`'s history JSONL to control the trend independently of the
  live volume. A perfectly linear -20GB/day slope with 50GB currently free
  (well above a 10GB floor) still yields `FAULT` because the 2-day runway
  is inside the 14-day window — the "healthy level, bad trend" case this
  probe exists for. A single sample yields `HEALTHY` with
  `detail["trend"] == "insufficient history"` and no `slope_gb_per_day`
  key. A 5-point series with one mid-series outlier (40GB dip amid
  ~80GB) keeps a non-negative least-squares slope and stays `HEALTHY` —
  proving the outlier doesn't flip the projection.
- Verification: `pytest tests/` — 19/19 passing (up from 11); `ruff check .`
  clean repo-wide. Built a scratch `python3.11` venv (`pyproject.toml`
  requires 3.11+; the ambient `python3` was 3.14) since none existed in the
  worktree yet.
- All 9 acceptance criteria checked off in `.paircoder/tasks/DM1.3.task.md`
  with the specific test (or command) that satisfies each; `bpsai-pair task
  update DM1.3 --status done` passed the strict AC gate on first attempt.

### Session: 2026-08-11 — DM1.2 evidence model + probe contract tests (`/start-task DM1.2`)

- The evidence model (`src/deadman/evidence/model.py`) and probe contract
  (`src/deadman/probes/base.py`) were already implemented as part of DM1.1's
  foundation work; this task locked their behavior down with tests rather
  than writing new implementation.
- `tests/test_evidence_model.py`: `Method` trust ordering (`DESTINATION_API`
  outranks `REPORTED`), `Evidence.provenance_row()` returns
  `(source, method, surface, iso_timestamp)`, `unobservable()` puts the
  reason in `detail` and merges any extra detail kwargs alongside it.
- `tests/test_probe_contract.py`: a raising probe yields `UNOBSERVABLE`
  (never `FAULT`) via `run_probe`; a probe returning a non-`Evidence` value
  is contained the same way; a well-behaved probe's evidence passes through
  unchanged; `sweep()` isolates one raising probe from the rest instead of
  taking the whole run down; `blind_spots()` returns only unobserved
  evidence and excludes healthy/fault entries.
- Verification: `pytest tests/` — 11/11 passing (up from 2 pre-existing
  hermetic-suite canaries); `ruff check` clean on both new files; `bpsai-pair
  arch check --strict` clean project-wide.
- All 7 acceptance criteria checked off in `.paircoder/tasks/DM1.2.task.md`
  with the test that satisfies each; `bpsai-pair task update DM1.2 --status
  done` passed the strict AC gate on first real attempt (after checking the
  boxes — the gate reads them from the task file, not from having tests
  merely exist).

### Session: 2026-08-10 — DM1.1 packaging, hermetic suite, CI (`/start-task DM1.1`)

- `pyproject.toml` (Python 3.11+, `deadman` package under `src/`) and
  `constraints.txt` pinned from a real resolve in a `python3.11` venv.
- `tests/conftest.py`: autouse fixture patches `socket.socket.connect` to
  raise `NetworkBlockedError` for every test; the `allow_network` marker
  (registered in `pyproject.toml`) is the only escape hatch, restoring the
  real `connect`.
- `tests/test_suite_is_hermetic.py`: two canary tests, both exercising the
  real socket layer rather than mocks — one asserts a real outbound attempt
  is blocked, the other (marked `allow_network`) asserts a real OS-level
  socket error comes through and is *not* `NetworkBlockedError`.
- Fixed the two defects flagged during planning: removed the unused
  `timedelta` import in `morning_brief.py` (F401), added `__init__.py` to
  `deadman/`, `deadman/probes/`, `deadman/evidence/`.
- `.github/workflows/ci.yml`: pytest, ruff check, `bpsai-pair arch check
  --strict` on push/PR to any branch.
- Wiring `arch check --strict` into CI surfaced two pre-existing violations
  (not introduced this session): `DiskProbe.observe` (77 lines) and
  `MorningBriefProbe.observe` (86 lines), both over the 50-line function
  limit. Split each into `observe()` + a `_trend_result`/`_age_result`
  helper — pure extraction, no behavior change, both probes' full test
  coverage is still DM1.3's job, not this task's.
- `.gitignore`: generalized `.venv-*` glob, added build output
  (`dist/`, `*.egg-info/`, cache dirs) and probe history artifacts
  (`*-history.jsonl`).
- Full CI job simulated locally end-to-end in a clean `python3.11` venv
  against the pinned constraints: pytest, ruff check, and
  `bpsai-pair arch check --strict` all pass.

### Session: 2026-08-10 — DM1 planning (`/pc-plan`)

- Read `plans/backlogs/DM1-deadman-v1.md` and `docs/SPRINT-BRIEF-DM1.md`.
- Registered all 12 tasks against the existing plan record and wrote full task
  bodies to `.paircoder/tasks/DM1.*.task.md` — objective, files, TDD-ordered
  implementation plan, acceptance criteria (backlog ACs plus wiring ACs for
  call site / configuration / failure modes), and verification commands.
- Resolved each `model:` via `bpsai-pair calibration recommend-model`
  (doctrine table; calibration store has insufficient samples). Deviations from
  the doctrine pick, all escalations: DM1.1 sonnet over haiku (foundation task,
  hermetic-suite canaries); DM1.4 and DM1.6 opus over sonnet (per backlog —
  spike judgment, and diagnosis-keyed action selection); DM1.12 opus over the
  backlog's sonnet (doctrine cross-module escalation, integration gate over all
  11 tasks).
- Marked DM1.8 `privileged: true` — live GCP infra and credentials.
- Found two concrete foundation defects while reading the existing source, both
  folded into DM1.1's plan: `src/deadman/probes/morning_brief.py:28` imports
  `timedelta` unused (F401 — fails the first CI ruff run), and `src/deadman/`
  has no `__init__.py` at any level despite `from deadman.*` imports.
- Gates run: `bpsai-pair validate` passed; `budget check` ok on every task
  (~2% of context each); `plan estimate` 297,750 tokens; `plan feasibility`
  REFUSED on DM1.1, DM1.2, DM1.5.

## What's Next

1. DM1.1 and DM1.2 are both `done`. Remaining wave-2 tasks (DM1.3, DM1.4,
   DM1.8, DM1.9) are unblocked and can proceed.

## Blockers

**0. RESOLVED — DM1.1's GitHub remote blocker.** `origin` now points at
`https://github.com/fivedollarfridays/deadman.git` and `bpsai-pair task show
DM1.1` reports `status: done`. The remote-creation decision this blocker was
waiting on was made outside this session; no action needed here.

**1. `plan feasibility` REFUSES DM1.1, DM1.2, DM1.5** (fail-closed gate).
Reason: downstream token risk if a hub task fails — 422,500 tokens behind
DM1.1, 198,500 behind DM1.2, 151,500 behind DM1.5. The gate prescribes
inserting intermediate checkpoint/commit tasks. All three already end in a
verified-green commit by their own ACs, which is arguably the checkpoint the
gate is asking for. **Not overridden — an override is audited to
`bypass_log.jsonl` and is the user's call:**

```bash
bpsai-pair plan feasibility plan-2026-08-dm1-deadman-v1 --override "<reason>"
```

**2. Sprint is 345 Cx against a 300 Cx budget (~15% over).** Per the planning
skill's scope rule this is Epic-shaped; the plan record is currently a Story.
Either accept the overrun, cut from the list above, or re-scope to an Epic.
<!-- paircoder:state:end -->
## Quick Commands

```bash
bpsai-pair status
bpsai-pair plan show plan-2026-08-dm1-deadman-v1
bpsai-pair plan tasks plan-2026-08-dm1-deadman-v1
bpsai-pair plan feasibility plan-2026-08-dm1-deadman-v1
bpsai-pair task update DM1.1 --status in_progress
bpsai-pair task update DM1.1 --status done
```
