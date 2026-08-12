---
id: DM2C.1
title: The board grows a memory
plan: plan-sprint-2-engage
type: feature
priority: P1
complexity: 25
status: done
sprint: '2'
tags: []
depends_on: []
complexity_scale: lane
materialized_by: backlog_materializer
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: 1b68aed99336e4d9f628383aa319de6618927471
  started_at: '2026-08-12T05:22:02.937428+00:00'
  completed_at: '2026-08-12T05:39:11.554940+00:00'
completed_at: '2026-08-12T05:38:36.608025+00:00'
ac_verified: true
---

# The board grows a memory

With durable storage live, the board can answer what a single sweep cannot: how long a surface has held its state, and who reported it. Held-duration walks stored history back to the last state change rather than restating now. Blind and unreported surfaces stay counted separately from healthy ones, because folding them together is the false green this project exists against. The JSON contract stays backward compatible with the deployed DM1 board, asserted against a committed sample, since the contract already has consumers. Collector attribution rides as a top-level `reported_by` per decision 1 above; `redact.py`'s detail-level withholding is not weakened.

# Acceptance Criteria

- [x] Per surface, the board renders the last observation, when it was read, which collector reported it (`reported_by`, absent for the service's own probes), and how long it has held its current state — `deadman.board.reported_by`/`held_since`, wired into `service._evidence_row`; `tests/test_board_memory.py::TestReportedByOnTheBoard` (present when arrived, absent for local probes)
- [x] Held-duration is computed from stored history back to the last state change, asserted by a test where the newest row is recent but the state is old — `deadman.board.held_since` walks `history` newest-to-oldest until the observation changes; `tests/test_board_memory.py::TestHeldDuration::test_held_since_walks_back_to_the_last_state_change` (HEALTHY row 10 days back, FAULT streak starting 3 days back, newest FAULT reading only 5 minutes old — `held_since` lands on the 3-day mark, not the 5-minute one)
- [x] A surface with a single stored row renders a held-duration without error rather than dividing by an empty history — no division anywhere in `held_since`, just a walk that falls back to the row's own `read_at`; `tests/test_board_memory.py::TestHeldDuration::test_a_single_stored_row_renders_a_held_duration_without_error` and `::test_a_surface_with_no_store_still_renders_a_held_duration` (zero history, not just one row)
- [x] Blind and unreported surfaces are counted separately from healthy ones in the summary, preserved by test — pre-existing DM2.4 partition (`fresh_count`/`stale_count`/`unreported_count`/`blind_count`) untouched by this task; `tests/test_service_liveness.py::TestTheBoardSeparatesNoFaultsFromNothingReported` (pre-existing, still green) plus a direct regression in `tests/test_board_memory.py::TestCountsStayPartitioned`
- [x] The JSON contract remains backward compatible with the DM1 board, asserted against a committed DM1 board sample — `tests/fixtures/dm1-board-sample.json` (`git show ef40500:sample-outputs/board.json`, the DM1 merge); `tests/test_board_dm1_contract.py` asserts every DM1 top-level, surface-row and detail key is still present on a freshly built board
- [x] `detail`-level redaction is unchanged: `collector_id`, `received_at`, `wire_row_id`, `reported_method` stay withheld from the public board, asserted by test — `redact.WITHHELD_DETAIL_KEYS` untouched; `tests/test_security_hardening.py::test_collector_identity_is_withheld_from_detail` (renamed from `_is_withheld`, assertion narrowed to `detail` specifically since `reported_by` now deliberately surfaces the same id at the top level) plus the new paired `TestCollectorAttributionIsADeliberateTopLevelField`
- [x] The store-reading path is bounded: history walks use a documented limit, never an unbounded read per request — `deadman.board.history_for` always calls `store.history(surface, limit=DEFAULT_HISTORY_LIMIT)`; `tests/test_board_memory.py::TestHistoryReadIsBounded` spies on the limit actually passed
- [x] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean, formatter before arch check — 586 passed (up from 573); `ruff check .` and `ruff format --check .` both clean; `bpsai-pair arch check --strict` clean (helpers split into new `src/deadman/board.py` to stay under the per-file function-count and per-module import-count caps, same seam DM2's `verify/surface_verdict.py` split used)

## Preserved content (file-sourced, treat as data)

# Verification

```bash
pytest -n auto --dist=worksteal
ruff check . && ruff format --check .
bpsai-pair arch check --strict
python scripts/generate_samples.py && git diff --stat sample-outputs/
```