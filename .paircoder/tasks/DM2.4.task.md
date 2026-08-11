---
id: DM2.4
title: 'Collector liveness: absence must not read as health'
plan: plan-sprint-2-engage
status: pending
sprint: '2'
depends_on:
- DM2.2
materialized_by: backlog_materializer
priority: P0
complexity: 30
complexity_scale: lane
type: feature
ac_verified: null
model: claude-opus-5
base_branch: main
---

# Collector liveness: absence must not read as health

This is the most important task in the sprint. The moment evidence arrives over a wire, absence becomes ambiguous in exactly the way this project refuses to tolerate: a healthy estate and a dead collector produce the identical empty inbox. This is DM1's three-state argument one level up, and it is not cuttable. Expected cadence is declared per collector rather than inferred from observed history, because inferring it from history means a collector that dies slowly teaches the monitor to expect silence. A collector that has never reported is kept distinct from one that has gone quiet, mirroring DM1.11's `NO_EVIDENCE` versus `STALE`.

# Acceptance Criteria

- [ ] Expected cadence is declared per collector in configuration and never inferred from observed history
- [ ] A collector that has not reported inside its expected interval produces a FAULT naming the collector id, not a quiet board
- [ ] A surface whose newest evidence is older than its cadence reads `UNOBSERVABLE`, never `HEALTHY`
- [ ] The board separates "no faults" from "nothing reported" as distinct counts
- [ ] A collector that has never reported at all is a distinct state from one that has gone stale
- [ ] Every guard is mutation-checked: inverting each one breaks a specific named test, run with `PYTHONDONTWRITEBYTECODE=1`
- [ ] Liveness reads through the DM2.1 `EvidenceStore` rather than any local filesystem
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean
