---
id: DM2.1
title: 'Evidence store: Protocol seam and a durable backend'
plan: plan-sprint-2-engage
status: done
sprint: '2'
depends_on: []
materialized_by: backlog_materializer
priority: P0
complexity: 35
complexity_scale: lane
type: feature
ac_verified: true
model: claude-opus-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: e51b7cd06e350236d8f4f1ed3c8e2f1fc06b7aed
  started_at: '2026-08-11T19:15:27.716060+00:00'
  completed_at: '2026-08-11T19:25:48.265368+00:00'
completed_at: '2026-08-11T19:24:37.337584+00:00'
---

# Evidence store: Protocol seam and a durable backend

Define `EvidenceStore` as a Protocol with two implementations behind it, an in-memory backend that every test uses and a Firestore backend for the deployed service. This is the contract consumed by ingest, liveness, the board and alerting, so the seam is the highest-leverage decision in the sprint: getting it wrong cascades into four downstream tasks. Firestore is the durable answer to DM1's known limitation that Cloud Run's per-instance filesystem loses all evidence on a cold start. The SDK import goes inside the constructor so the core package stays importable with zero dependencies installed.

# Acceptance Criteria

- [x] `src/deadman/store/base.py` defines an `EvidenceStore` Protocol covering append and read-latest-per-surface with no SDK import at module scope
- [x] `src/deadman/store/memory.py` satisfies the Protocol and is the backend every test uses
- [x] `src/deadman/store/firestore.py` imports the Firestore SDK inside the constructor, matching the `GeminiClient` seam pattern already in the repo
- [x] `pyproject.toml` still declares `dependencies = []` and Firestore lands behind an optional extra
- [x] `python -c "import deadman.store"` succeeds in an environment with no optional extras installed
- [x] `tests/test_store_contract.py` runs one contract suite against every registered backend so a new backend cannot silently diverge
- [x] Append then read-latest-per-surface round trips preserving `surface`, `observation`, `method`, `read_at` and `detail`
- [x] Reading a surface with no stored rows returns an explicit absence, never a synthesized healthy row
- [x] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean

# Evidence

- **Protocol seam** — `EvidenceStore` in `src/deadman/store/base.py`: `append`,
  `latest`, `latest_per_surface`, `history`. `runtime_checkable`, asserted per
  backend by `test_backend_satisfies_the_protocol`. Shared `encode`/`decode`
  live here so two backends cannot disagree about how a `Method` persists.
- **Absence is a state, not a null** — `latest()` on an unreported surface
  returns `unobservable(...)`, never `None` and never a healthy row.
  Mutation-checked: synthesising a `HEALTHY` row fails
  `test_reading_a_surface_with_no_rows_returns_an_explicit_absence` on both
  backends.
- **Firestore seam** — SDK imported inside `__post_init__`, `StoreSdkMissing`
  raised at construction, mirroring `GeminiClient`. Guarded two ways by
  `tests/test_store_seam.py`: an AST scan that fails on any module-scope
  `google` import (verified to fire on an injected import), and a subprocess
  that imports `deadman.store` and asserts no `google.*` reached `sys.modules`.
- **The Firestore backend is contract-tested, not just written** — the backend
  accepts an injected client, and `tests/firestore_double.py` reproduces the
  narrow API slice it calls, including the two behaviours that would otherwise
  only fail in production: document ids may not contain `/` (surface
  `host:mac/disk` does), and a collection query skips documents that exist only
  as subcollection parents.
- **Six mutation checks, each caught by a named test** (`PYTHONDONTWRITEBYTECODE=1`):
  surface key unencoded → `test_append_then_read_latest_round_trips_every_field[firestore]`;
  Firestore ordering ascending → 3 tests; memory ordered by arrival →
  `test_latest_is_the_newest_by_read_at_not_the_last_appended[memory]`;
  absence synthesised healthy → 2 tests; row identity by surface only → 6 tests;
  dedup removed → `test_appending_an_identical_row_twice_stores_it_once[memory]`.
- **Zero dependencies held** — `.venv` has no `google*` package;
  `import deadman.store` succeeds and reports both backends.
  `test_pyproject_keeps_zero_runtime_dependencies_and_puts_firestore_in_an_extra`
  asserts `dependencies == []`, that `firestore` is an extra, and that it is
  not in `dev`.
- **Gates** — `pytest -n auto --dist=worksteal`: 265 passed (236 before, 29
  new). `ruff check .` clean, `ruff format --check .` clean (68 files),
  `bpsai-pair arch check --strict` clean.

## Handoff to downstream tasks

- **Replay safety is already in the store.** `row_id()` derives a
  content-addressed id, so appending an identical row twice stores it once and
  a document backend writes with `set` rather than a read-modify-write race.
  DM2.2's idempotent-batch AC gets this for free; rows differing only in
  `read_at` are deliberately kept apart, which is what DM2.8's held-duration
  needs.
- **`history()` exists for DM2.8** and is contract-tested now — newest `limit`
  rows, oldest first — so the board's memory does not require reopening this
  Protocol.
- **`latest_per_surface()` reports only surfaces that have reported.** It does
  not invent entries for silent ones: reconciling declared surfaces against
  reported ones is DM2.4's job and it needs the two kept apart.
- **The Dockerfile still installs `.` with no extras.** Nothing constructs a
  `FirestoreEvidenceStore` yet, so the image is correct today. Whichever of
  DM2.2/DM2.6 first wires Firestore into the deployed service must change it to
  `.[firestore]`, or the service will fail closed at startup with
  `StoreSdkMissing` — loudly, by design, but on the deploy rather than in CI.