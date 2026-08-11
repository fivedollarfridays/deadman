# DM2 — make it real

**Base:** main

DM1 built a monitor that has never monitored anything. It is a library, a test
suite, and an endpoint that sweeps when a human sends it a GET. Nothing runs on
a cadence, nothing survives a cold start, and zero surfaces watch real
infrastructure.

DM2 makes it real: sweeps that run on their own, evidence that persists, real
surfaces on Kevin's actual machines, and an alarm that reaches him. The goal is
a tool he relies on daily. A contest submission is a side effect of that.

Target: All Things Agentic, Taskmaster category, deadline 2026-08-31 5:00pm PDT.
Brief: `docs/SPRINT-BRIEF-DM2.md`

**The finding that justifies the sprint.** Pointing the existing
`MorningBriefProbe` at `~/ops/data/brief-send-log.jsonl` with no new code
returned FAULT immediately: no brief sent since 2026-08-04 06:56, seven days,
undetected, because the brief is itself the alerting channel and a dead brief
cannot report its own death.

**The central architectural fact.** The surfaces are not where the service is.
Cloud Run cannot read a log on the Mac, and opening inbound access to a laptop
is the wrong answer. So DM2 splits into a **collector** that runs where the
surfaces live and ships evidence to an authenticated ingest endpoint, and the
hosted **service** that stores, correlates and alerts. This is a topology
change, not a config change, and it drives the dependency graph.

**Zero runtime dependencies is a commitment, not an accident.**
`pyproject.toml` declares `dependencies = []`. Every new backend follows the
established seam: an optional extra plus a Protocol with the SDK imported
inside the constructor, as `GeminiClient` already does. The core stays
importable with nothing installed.

**Evidence crossing a wire changes its provenance.** A collector reading a log
locally produced `LOCAL_ARTIFACT`; the service receives a *report of* that
reading. Silently upgrading the method on arrival reintroduces the heartbeat
this project exists to argue against.

## Phase 1: The store everything else stands on

### DM2.1 — Evidence store: Protocol seam and a durable backend | Cx: 35 | P0

**Description:** Define `EvidenceStore` as a Protocol with two implementations behind it, an in-memory backend that every test uses and a Firestore backend for the deployed service. This is the contract consumed by ingest, liveness, the board and alerting, so the seam is the highest-leverage decision in the sprint: getting it wrong cascades into four downstream tasks. Firestore is the durable answer to DM1's known limitation that Cloud Run's per-instance filesystem loses all evidence on a cold start. The SDK import goes inside the constructor so the core package stays importable with zero dependencies installed.

**AC:**
- [ ] `src/deadman/store/base.py` defines an `EvidenceStore` Protocol covering append and read-latest-per-surface with no SDK import at module scope
- [ ] `src/deadman/store/memory.py` satisfies the Protocol and is the backend every test uses
- [ ] `src/deadman/store/firestore.py` imports the Firestore SDK inside the constructor, matching the `GeminiClient` seam pattern already in the repo
- [ ] `pyproject.toml` still declares `dependencies = []` and Firestore lands behind an optional extra
- [ ] `python -c "import deadman.store"` succeeds in an environment with no optional extras installed
- [ ] `tests/test_store_contract.py` runs one contract suite against every registered backend so a new backend cannot silently diverge
- [ ] Append then read-latest-per-surface round trips preserving `surface`, `observation`, `method`, `read_at` and `detail`
- [ ] Reading a surface with no stored rows returns an explicit absence, never a synthesized healthy row
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean

**Depends on:** None
**Model:** claude-opus-5

## Phase 2: The wire in, and the alarm out

### DM2.2 — Authenticated ingest, and what a reported observation means | Cx: 35 | P0

**Description:** Add `POST /evidence` so a collector can ship a signed batch to the service, and encode the provenance rule that makes remote evidence honest. The interesting part is not the HTTP: it is that a report of a local reading is a weaker claim than the reading, and the method must not be upgraded on arrival. Replay safety matters because a collector that cannot reach the service will re-send, so a duplicated batch must not double the history and manufacture a false trend. Auth fails closed: a missing shared secret refuses to start rather than quietly accepting unsigned batches.

**AC:**
- [ ] `POST /evidence` accepts a correctly signed batch and stores every row through the DM2.1 `EvidenceStore`
- [ ] An unsigned or wrongly signed batch is rejected with an auth failure and stores nothing
- [ ] A batch whose signature timestamp falls outside the freshness window is rejected as stale
- [ ] Every stored row carries `collector_id` and an arrival time as fields distinct from `read_at`
- [ ] The method is never upgraded on arrival, asserted by a test that fails if the arrival mapping is made the identity function
- [ ] A replayed identical batch is idempotent: history length is unchanged, asserted by a test
- [ ] The shared secret is read from the environment, never committed, and a missing secret fails closed at startup rather than accepting unsigned batches
- [ ] `src/deadman/ingest/wire.py` round trips `Evidence` without losing provenance, including `Method` and `detail`
- [ ] A malformed or oversized body is rejected as a 4xx rather than raising a 500
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean

**Depends on:** DM2.1
**Model:** claude-opus-5

### DM2.7 — An alarm that actually reaches Kevin | Cx: 30 | P0

**Description:** DM1.11 built `AlertChannel` with a startup refusal to sit on a rail deadman watches, but nothing real is wired to it. This task delivers an email transport over the existing ops rail and runs the out-of-band assertion against the real monitored surface list, so misconfiguration is caught at startup rather than at the moment the alarm is needed. Throttling is required because a persistent fault sweeps every cadence, but a throttle that swallows a state change is worse than no throttle: the transition from fault to healthy, or healthy to fault, must always get through. A transport that fails is itself evidence and gets stored rather than swallowed.

**AC:**
- [ ] An email transport delivers through the existing ops email rail and one real message is confirmed received
- [ ] The out-of-band assertion runs against the real monitored surface list rather than a literal, so wiring the alarm to a watched rail raises at construction
- [ ] A test wires the alarm to a monitored rail and asserts the construction-time refusal
- [ ] Repeated identical alerts are throttled by a documented window
- [ ] A state change inside the throttle window is always delivered, asserted by a test that flips state mid-window
- [ ] A transport failure is recorded as evidence through the DM2.1 store rather than swallowed
- [ ] `docs/alerting.md` documents the rail, the throttle window, and why the rail is out of band relative to every monitored surface
- [ ] Credentials for the rail come from the environment and are absent from the repo
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean

**Depends on:** DM2.1
**Model:** claude-sonnet-5

## Phase 3: The collector, and proof it is alive

### DM2.3 — The collector: sweep where the surfaces actually are | Cx: 35 | P0

**Description:** Build the process that runs on Kevin's machines, sweeps the local surfaces, and ships a signed batch to the ingest endpoint. Which probes run is configuration, not code, because the whole point is that adding a surface on a new machine does not mean editing the collector. Store-and-forward is non-negotiable: an unreachable service must never cause evidence to be dropped, since a network blip would then look exactly like a healthy estate. Dry-run exists so the thing can be inspected before it is trusted with a real rail.

**AC:**
- [ ] `src/deadman/collector/config.py` reads which probes to run, and their arguments, from a config file rather than from code
- [ ] A probe that raises is contained and the remaining surfaces' evidence still ships, matching the `run_probe` contract
- [ ] An unreachable service writes the batch to a local spool and re-sends it on a later run, never dropping it
- [ ] The spool survives process restart, asserted by a test that reconstructs the collector from disk
- [ ] `--dry-run` prints the batch it would ship and makes zero network calls, asserted under the hermetic socket block
- [ ] The collector signs its batch with the DM2.2 wire format and attaches its own collector id
- [ ] `infra/launchd/com.deadman.collector.plist` installs on the Mac with one documented command in the README
- [ ] A malformed config fails loudly at startup naming the offending key, rather than silently sweeping nothing
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean

**Depends on:** DM2.2
**Model:** claude-sonnet-5

### DM2.4 — Collector liveness: absence must not read as health | Cx: 30 | P0

**Description:** This is the most important task in the sprint. The moment evidence arrives over a wire, absence becomes ambiguous in exactly the way this project refuses to tolerate: a healthy estate and a dead collector produce the identical empty inbox. This is DM1's three-state argument one level up, and it is not cuttable. Expected cadence is declared per collector rather than inferred from observed history, because inferring it from history means a collector that dies slowly teaches the monitor to expect silence. A collector that has never reported is kept distinct from one that has gone quiet, mirroring DM1.11's `NO_EVIDENCE` versus `STALE`.

**AC:**
- [ ] Expected cadence is declared per collector in configuration and never inferred from observed history
- [ ] A collector that has not reported inside its expected interval produces a FAULT naming the collector id, not a quiet board
- [ ] A surface whose newest evidence is older than its cadence reads `UNOBSERVABLE`, never `HEALTHY`
- [ ] The board separates "no faults" from "nothing reported" as distinct counts
- [ ] A collector that has never reported at all is a distinct state from one that has gone stale
- [ ] Every guard is mutation-checked: inverting each one breaks a specific named test, run with `PYTHONDONTWRITEBYTECODE=1`
- [ ] Liveness reads through the DM2.1 `EvidenceStore` rather than any local filesystem
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean

**Depends on:** DM2.2
**Model:** claude-opus-5

## Phase 4: Real surfaces on a real cadence

### DM2.5 — Real surfaces, starting with the one that is already broken | Cx: 30 | P0

**Description:** Wire the collector to actual infrastructure, beginning with the morning brief log that is broken right now. This is the task that converts deadman from a demonstration into a tool, and the acceptance test is not synthetic: the surface must report the real, current fault. Capturing that output is also what makes DM2.9's case study written from evidence rather than from memory. Disk trend watches the Mac and the rig as separate surfaces, because a full volume on one says nothing about the other. Every path is configuration, so nothing about Kevin's filesystem is compiled into the package.

**AC:**
- [ ] The morning brief surface watches `~/ops/data/brief-send-log.jsonl` and reports the current, real fault
- [ ] The captured output of that real FAULT is committed as a fixture, for DM2.9 to write the case study from
- [ ] Disk trend watches the Mac volume and the rig volume as separate surfaces with distinct stable surface ids
- [ ] Every surface's real path comes from collector configuration, never a hardcoded literal, asserted by a test
- [ ] A missing path reads `UNOBSERVABLE` with the path named in `detail`, never `FAULT`
- [ ] `docs/surfaces.md` lists each real surface, its path, its declared cadence, and what its blindness would mean
- [ ] Adding a surface is a config edit plus an existing probe, demonstrated by the second disk surface needing no new probe code
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean

**Depends on:** DM2.3
**Model:** claude-sonnet-5

### DM2.6 — Scheduled sweeps and scheduled self-check | Cx: 25 | P0

**Description:** Nothing in DM1 runs on its own. This task enables Cloud Scheduler on `deadman-20260810`, creates the job, and gives the service a self-check on that cadence whose evidence is durable rather than per-instance, retiring DM1.11's stated cold-start limitation. The scheduled endpoint is authenticated and separate from the public board, because a public endpoint that triggers work is a free denial-of-service. The collector keeps its own local timer deliberately: two independent clocks mean one dying does not silence the other, which is the whole redundancy argument. This task touches live billable cloud infrastructure and is privileged. Deploy follows merge, or the deployed image tag goes stale.

**AC:**
- [ ] Cloud Scheduler API enabled on `deadman-20260810` and a job created, with the exact reproducible commands recorded in `infra/scheduler.md`
- [ ] The scheduled endpoint requires authentication and is not the public board endpoint
- [ ] An unauthenticated request to the scheduled endpoint is rejected, asserted by a test
- [ ] The service's own self-check runs on that cadence and writes self-evidence through the DM2.1 store
- [ ] A test proves self-evidence is read from the store rather than from the per-instance filesystem, so it survives a cold start
- [ ] The collector runs on its own local timer independently of Cloud Scheduler, documented so that one dying does not silence the other
- [ ] The scheduler job is verified to have actually fired at least once, evidenced by a stored row rather than by the job's own status
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean

**Depends on:** DM2.4
**Model:** claude-sonnet-5

## Phase 5: The board remembers

### DM2.8 — The board grows a memory | Cx: 25 | P1

**Description:** With durable storage in place the board can answer questions a single sweep cannot: how long a surface has held its state, and who reported it. Held-duration comes from stored history rather than from the current sweep, otherwise it is just a restatement of now. Blind and unreported surfaces are counted separately from healthy ones, because a summary that folds them together is precisely the false green this project exists to prevent. Backward compatibility with the DM1 board JSON is asserted against a committed sample, since the deployed contract already has a consumer.

**AC:**
- [ ] Per surface, the board renders the last observation, when it was read, which collector reported it, and how long it has held that state
- [ ] Held-duration is computed from stored history rather than from the current sweep
- [ ] Blind and unreported surfaces are counted separately from healthy ones in the summary
- [ ] The JSON contract remains backward compatible with the DM1 board, asserted against a committed DM1 board sample
- [ ] A surface with a single stored row renders a held-duration without error rather than dividing by an empty history
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean

**Depends on:** DM2.6
**Model:** claude-sonnet-5

## Phase 6: Proof

### DM2.9 — Integration gate and the real-world proof writeup | Cx: 30 | P0

**Description:** Close the sprint by proving the whole thing works together and writing the case study that is the actual argument for the project. `docs/PROOF.md` documents the morning brief outage from captured output committed in the repo, never from memory, and states the detection latency deadman now achieves against the seven days the real outage took to find by accident. The demo's break-and-heal must run against a real surface rather than the stub, because a scripted failure proves only that the script works. The architecture diagram gets the collector and service split it did not have.

**AC:**
- [ ] `docs/PROOF.md` documents the morning brief outage as a case study with the evidence, the timeline, and the detection, written from captured output committed in the repo rather than from memory
- [ ] The case study states the detection latency deadman now achieves against the seven days the real outage went unnoticed
- [ ] `sample-outputs/` is regenerated by script and enforced byte for byte by a test
- [ ] The demo's break-and-heal sequence runs against at least one real surface rather than the stub
- [ ] `README.md` spin-up instructions reproduce from a clean clone, verified by running them verbatim
- [ ] The architecture diagram shows the collector and service split, including which side of the wire each surface is read on
- [ ] Full suite green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean, in that order with arch check after the formatter
- [ ] A clean clone of the merge commit reproduces the suite and the documented deploy

**Depends on:** DM2.1, DM2.2, DM2.3, DM2.4, DM2.5, DM2.6, DM2.7, DM2.8
**Model:** claude-opus-5

## Delivery Summary

| ID | Title | Cx | Pri | Model | Depends on |
|---|---|---|---|---|---|
| DM2.1 | Evidence store: Protocol seam and a durable backend | 35 | P0 | claude-opus-5 | — |
| DM2.2 | Authenticated ingest, and what a reported observation means | 35 | P0 | claude-opus-5 | DM2.1 |
| DM2.7 | An alarm that actually reaches Kevin | 30 | P0 | claude-sonnet-5 | DM2.1 |
| DM2.3 | The collector: sweep where the surfaces actually are | 35 | P0 | claude-sonnet-5 | DM2.2 |
| DM2.4 | Collector liveness: absence must not read as health | 30 | P0 | claude-opus-5 | DM2.2 |
| DM2.5 | Real surfaces, starting with the one that is already broken | 30 | P0 | claude-sonnet-5 | DM2.3 |
| DM2.6 | Scheduled sweeps and scheduled self-check | 25 | P0 | claude-sonnet-5 | DM2.4 |
| DM2.8 | The board grows a memory | 25 | P1 | claude-sonnet-5 | DM2.6 |
| DM2.9 | Integration gate and the real-world proof writeup | 30 | P0 | claude-opus-5 | all |

**Total Cx:** 275 — 9 tasks, 8 P0, 1 P1, 0 P2.

## Priority Order

1. DM2.1 — nothing else can land without the store contract
2. DM2.2 — the wire format gates the collector
3. DM2.7 — independent of the wire, so it runs beside DM2.2
4. DM2.3 — the collector itself
5. DM2.4 — collector liveness, the single least cuttable task in the sprint
6. DM2.5 — real surfaces, the task that makes deadman a tool
7. DM2.6 — cadence, and durable self-evidence
8. DM2.8 — board memory, the only cuttable task
9. DM2.9 — integration gate and the proof writeup

## Waves

```
Wave 0:  DM2.1
Wave 1:  DM2.2   DM2.7
Wave 2:  DM2.3   DM2.4
Wave 3:  DM2.5   DM2.6
Wave 4:  DM2.8
Wave 5:  DM2.9
```

## File Collision Matrix

| Wave | Tasks in parallel | Intersection |
|---|---|---|
| 1 | DM2.2, DM2.7 | none — `ingest/` + `service.py` vs `remediate/transports.py` |
| 2 | DM2.3, DM2.4 | none — `collector/` vs `verify/collector_liveness.py` |
| 3 | DM2.5, DM2.6 | none — `collector/surfaces.py` vs `service.py` + `infra/` |

DM2.6 and DM2.8 both edit `src/deadman/service.py`, resolved by making DM2.8
depend on DM2.6 rather than run beside it, which costs one wave and removes the
conflict. DM2.2 also touches `service.py` but lands two waves earlier.

## Cut List

DM2.8 first, then DM2.5's disk surfaces leaving only the morning brief.
**Nothing else is cuttable.** Cutting DM2.4 would ship a monitor whose silence
is ambiguous, which is worse than shipping nothing.

## Out of Scope

- Grounding reliability and the 1-in-4 ungrounded rate, including measuring it across 50+ live calls rather than 4 — DM3
- The live correlation demo — DM3
- Metricool and the phone relay as real surfaces, both of which need credentials and a destination read
- Fixing `morning_brief_send.py`, which is an `ops` repo bug; deadman's job is to notice it, and it already does
- Retiring the seven existing point-solution monitors
- A general surface registry; adding a surface still means writing a probe
