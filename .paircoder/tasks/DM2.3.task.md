---
id: DM2.3
title: 'The collector: sweep where the surfaces actually are'
plan: plan-sprint-2-engage
status: pending
sprint: '2'
depends_on:
- DM2.2
materialized_by: backlog_materializer
priority: P0
complexity: 35
complexity_scale: lane
type: feature
ac_verified: null
model: claude-sonnet-5
base_branch: main
---

# The collector: sweep where the surfaces actually are

Build the process that runs on Kevin's machines, sweeps the local surfaces, and ships a signed batch to the ingest endpoint. Which probes run is configuration, not code, because the whole point is that adding a surface on a new machine does not mean editing the collector. Store-and-forward is non-negotiable: an unreachable service must never cause evidence to be dropped, since a network blip would then look exactly like a healthy estate. Dry-run exists so the thing can be inspected before it is trusted with a real rail.

# Acceptance Criteria

- [ ] `src/deadman/collector/config.py` reads which probes to run, and their arguments, from a config file rather than from code
- [ ] A probe that raises is contained and the remaining surfaces' evidence still ships, matching the `run_probe` contract
- [ ] An unreachable service writes the batch to a local spool and re-sends it on a later run, never dropping it
- [ ] The spool survives process restart, asserted by a test that reconstructs the collector from disk
- [ ] `--dry-run` prints the batch it would ship and makes zero network calls, asserted under the hermetic socket block
- [ ] The collector signs its batch with the DM2.2 wire format and attaches its own collector id
- [ ] `infra/launchd/com.deadman.collector.plist` installs on the Mac with one documented command in the README
- [ ] A malformed config fails loudly at startup naming the offending key, rather than silently sweeping nothing
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean
