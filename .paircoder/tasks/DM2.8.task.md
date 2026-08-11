---
id: DM2.8
title: The board grows a memory
plan: plan-sprint-2-engage
status: pending
sprint: '2'
depends_on:
- DM2.6
materialized_by: backlog_materializer
priority: P1
complexity: 25
complexity_scale: lane
type: feature
ac_verified: null
model: claude-sonnet-5
base_branch: main
---

# The board grows a memory

With durable storage in place the board can answer questions a single sweep cannot: how long a surface has held its state, and who reported it. Held-duration comes from stored history rather than from the current sweep, otherwise it is just a restatement of now. Blind and unreported surfaces are counted separately from healthy ones, because a summary that folds them together is precisely the false green this project exists to prevent. Backward compatibility with the DM1 board JSON is asserted against a committed sample, since the deployed contract already has a consumer.

# Acceptance Criteria

- [ ] Per surface, the board renders the last observation, when it was read, which collector reported it, and how long it has held that state
- [ ] Held-duration is computed from stored history rather than from the current sweep
- [ ] Blind and unreported surfaces are counted separately from healthy ones in the summary
- [ ] The JSON contract remains backward compatible with the DM1 board, asserted against a committed DM1 board sample
- [ ] A surface with a single stored row renders a held-duration without error rather than dividing by an empty history
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean
