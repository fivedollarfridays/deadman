---
id: DM3.2
title: Pin the Mac collector to a promoted checkout
plan: plan-2026-08-dm3-2-pin-collector
type: chore
priority: P1
complexity: 3
status: in_progress
sprint: null
tags: []
depends_on: []
complexity_scale: points
runtime:
  pre_task_sha:
    deadman: 89d206ca22898b90f957c4c26892a8d5d1613977
---

# Objective

`git checkout` in the dev tree must never change what the collector executes.

# Context — found while shipping DM3.1

`~/Library/LaunchAgents/com.deadman.collector.plist` execs:

```
/Users/kevinmasterson/Projects/deadman/.venv/bin/deadman-collector
```

and that venv holds `__editable__.deadman-0.1.0.pth` → `~/Projects/deadman/src`.
**The production collector therefore runs whatever branch the dev checkout is
standing on.**

This was not theoretical. While verifying DM3.1 the fix appeared "live" only
because the checkout happened to still be on the fix branch; switching branches
would have silently reverted the outside watcher to crashing code, with no
signal anywhere. The checkout was moved to `main` as a stopgap — **that is not a
fix, it is a coincidence being maintained by hand.**

## The pattern this is the third instance of

Production state or code living inside a git checkout, where an ordinary git
operation destroys or mutates it:

1. **kai-studio devpost series** — the tracker wrote inside the checkout and
   every promote ran `git checkout -f --detach origin/main`, resetting it.
   Their own comment records the cost: *"six green cron runs, one surviving
   row."* FIXED by moving to `~/kai-studio-data/` (HACKRUN.3).
2. **kai-studio prod venv** — editable install pointing at the DEV checkout;
   `run-devpost.sh` failed for weeks. FIXED 2026-08-21.
3. **this** — and it is the one watching everything else. **The watcher is the
   least protected component in the estate.**

kai-studio already solved this shape with `scripts/promote-prod.sh`: a separate
clone, detached HEAD at an explicit pinned commit, promotion always deliberate,
nothing on a schedule. Mirror it rather than invent a second pattern.

# Implementation Plan

1. `~/prod/deadman` — separate clone, detached at an explicit SHA.
2. Its own venv with a **NON-editable** install (`pip install .`), so the venv
   holds its own copy and no `.pth` can reach back into a working tree.
3. `scripts/promote-collector.sh` mirroring promote-prod.sh's interface:
   `<ref>` to promote, `--status`, `--rollback`; previous ref persisted.
4. Repoint the launchd plist at the prod venv; reload.
5. Prove the isolation, do not assume it: with the collector pinned, check out a
   different branch in the dev tree and confirm the collector's resolved module
   path and behaviour are unchanged.

# Acceptance Criteria

- [x] Collector runs from `~/prod/deadman`, never `~/Projects/deadman`
- [x] The prod venv has NO `__editable__*.pth` — asserted, not eyeballed
- [x] `promote-collector.sh` supports promote / `--status` / `--rollback`, and records the previous ref
- [x] **Isolation proven:** dev tree switched to another branch, collector's resolved `deadman.__file__` and probe behaviour unchanged
- [x] launchd plist points at the prod venv and the job is loaded
- [x] Collector still reports to the board after the switch (surfaces stay healthy, `collector:kevin-mac` fresh)
- [x] Dev workflow unbroken: `~/Projects/deadman/.venv` still editable for tests

# Verification

- `ls ~/prod/deadman/.venv/lib/python*/site-packages/ | grep __editable__` → empty
- Dev-tree branch switch → collector module path unchanged
- Board shows `collector:kevin-mac` healthy after the cutover
- `promote-collector.sh --status` names the pinned SHA