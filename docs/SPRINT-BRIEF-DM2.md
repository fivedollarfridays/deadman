# Feature Brief: DM2 — make it real

## Idea

DM1 built a monitor that has never monitored anything. It is a library, a test
suite, and an endpoint that sweeps when a human sends it a GET. Nothing runs on
a cadence, nothing survives a cold start, and zero surfaces watch real
infrastructure.

DM2 makes it real: sweeps that run on their own, evidence that persists, real
surfaces on Kevin's actual machines, and an alarm that reaches him. The goal is
a tool he relies on daily. A contest submission is a side effect of that, not
the target.

**The finding that justifies the sprint.** During ideation, the existing
`MorningBriefProbe` was pointed at `~/ops/data/brief-send-log.jsonl` with no new
code and immediately returned FAULT: no brief sent in 162.8h, roughly six
missed. Verified: `com.cognify.morning-brief` is loaded and fires daily at
6:00am, `morning_brief_send.py` hangs, exceeds its 2700s deadline, and is killed
by its own hang guard. Last exit status 124. Last brief actually delivered
2026-08-04 06:56. **Seven days dead, undetected, because the brief is the
alerting channel and a dead brief cannot report its own death.**

That is the doctrine's canonical failure, live, in the estate this was built
for. DM2 exists so the next one is caught in minutes rather than found by
accident during a planning session.

## Codebase Context

- **Stack:** Python 3.11+, zero runtime dependencies, Gemini via ADK behind an
  optional extra, Cloud Run + Cloud Build, hermetic socket-blocked test suite.
- **Size:** 30 source modules, 24 test files, 236 tests. Largest source file 246
  lines, comfortably inside the 400/200 arch caps.
- **Current sprint:** DM1 complete, 12 of 12, merged. Deployed at
  https://deadman-mrapac5nda-uc.a.run.app tagged with the commit SHA.
- **Conflicting in-progress tasks:** none. `validate` and `doctor` both pass.

## Sprint-Level Constraints

These are the decisions `/pc-plan` cannot make because each is only visible
across several tasks at once.

**1. The surfaces are not where the service is.** This is the central
architectural fact of DM2 and it was not accounted for in DM1. The brief log is
on the Mac. Disk trend matters on the Mac and the rig. The phone relay is
reachable over Tailscale from the Mac, not from Google's network. Cloud Run
cannot read any of them, and opening inbound access to a laptop is the wrong
answer.

So DM2 must split into **collector and service**. A collector runs where the
surfaces live, sweeps locally, and ships evidence outward to an authenticated
ingest endpoint. The hosted service stores, correlates, alerts, and remains the
visible Google Cloud component. This is a topology change, not a config change,
and it drives most of the dependency graph below.

**2. A collector that dies must not look like silence.** The moment evidence
arrives over a wire, absence of evidence becomes ambiguous in exactly the way
this project refuses to tolerate: a healthy estate and a dead collector both
produce an empty inbox. Collector liveness is therefore P0, not a nicety, and
it is the same three-state argument one level up. This is the single most
important task in the sprint and the easiest to leave until last by mistake.

**3. Zero runtime dependencies is a real commitment, not an accident.**
`pyproject.toml` declares `dependencies = []`, and both `service.py` and
`gemini.py` document why. A Firestore client, an HTTP client, and an email
transport all threaten it. The established pattern is already in the repo:
optional extras plus a Protocol seam with the SDK imported inside the
constructor, as `GeminiClient` does. Every new backend in DM2 follows it, and
the core stays importable with nothing installed. If a task cannot meet that,
it should say so rather than quietly add a dependency.

**4. Evidence crossing a wire changes its provenance.** The trust model ranks
how a fact was learned. A collector reading a log locally produced
`LOCAL_ARTIFACT`, but the service receives a *report of* that reading. The
method must not be silently upgraded on arrival, and every stored row needs the
collector identity attached. Getting this wrong quietly reintroduces the
heartbeat this project exists to argue against.

**5. Cross-task contract edges.** `EvidenceStore` (DM2.1) is consumed by ingest,
liveness, the board, and alerting. The wire format (DM2.2) is consumed by the
collector. Both must land before their consumers, which is what the waves below
encode.

## Tasks

**DM2.1 — Evidence store: Protocol seam and a durable backend**
- Cx: 35 · Priority: **P0** · Depends on: none
- Files: `src/deadman/store/base.py`, `src/deadman/store/memory.py`,
  `src/deadman/store/firestore.py`, `tests/test_store_contract.py`
- AC template: schema
- Custom AC: core imports with zero dependencies installed; an in-memory
  backend satisfies the same contract and is what tests use; append and
  read-latest-per-surface round trip; the contract test runs against every
  backend so a new one cannot silently diverge.

**DM2.2 — Authenticated ingest, and what a reported observation means**
- Cx: 35 · Priority: **P0** · Depends on: DM2.1
- Files: `src/deadman/service.py`, `src/deadman/ingest/wire.py`,
  `src/deadman/ingest/auth.py`, `tests/test_ingest.py`
- AC template: schema
- Custom AC: `POST /evidence` accepts a signed batch and rejects an unsigned or
  stale one; every stored row carries the collector id and the arrival time
  separately from `read_at`; **the method is never upgraded on arrival**; a
  replayed batch is idempotent rather than doubling the history.

**DM2.3 — The collector: sweep where the surfaces actually are**
- Cx: 35 · Priority: **P0** · Depends on: DM2.2
- Files: `src/deadman/collector/run.py`, `src/deadman/collector/config.py`,
  `infra/launchd/com.deadman.collector.plist`, `tests/test_collector.py`
- AC template: gate
- Custom AC: reads which probes to run from config rather than code; a probe
  that raises still ships the other surfaces' evidence; **an unreachable
  service is recorded locally and re-sent, never dropped**; dry-run prints what
  it would ship; installable on the Mac with one documented command.

**DM2.4 — Collector liveness: absence must not read as health**
- Cx: 30 · Priority: **P0** · Depends on: DM2.2
- Files: `src/deadman/verify/collector_liveness.py`,
  `tests/test_collector_liveness.py`
- AC template: gate
- Custom AC: a collector that has not reported inside its expected interval
  produces a FAULT naming the collector, not a quiet board; a surface whose
  last evidence is older than its cadence reads `UNOBSERVABLE`, never
  `HEALTHY`; the board separates "no faults" from "nothing reported"; expected
  cadence is declared per collector rather than guessed.

**DM2.5 — Real surfaces, starting with the one that is already broken**
- Cx: 30 · Priority: **P0** · Depends on: DM2.3
- Files: `src/deadman/collector/surfaces.py`, `docs/surfaces.md`,
  `tests/test_collector_surfaces.py`
- AC template: migration
- Custom AC: the morning brief surface watches `~/ops/data/brief-send-log.jsonl`
  and reports the **current, real** fault; disk trend watches the Mac volume
  and the rig; every surface's real path is config, never hardcoded; a missing
  path reads `UNOBSERVABLE` with the path named, not `FAULT`.

**DM2.6 — Scheduled sweeps and scheduled self-check**
- Cx: 25 · Priority: **P0** · Depends on: DM2.4
- Files: `infra/scheduler.md`, `src/deadman/service.py`,
  `tests/test_service_schedule.py`
- AC template: gate
- Custom AC: Cloud Scheduler API enabled and a job created, documented as
  reproducible commands; the scheduled endpoint requires auth and is not the
  public board; **the service's own self-check runs on that cadence** and its
  evidence is durable rather than per-instance; the collector runs on its own
  local timer independently, so one dying does not silence the other.

**DM2.7 — An alarm that actually reaches Kevin**
- Cx: 30 · Priority: **P0** · Depends on: DM2.1
- Files: `src/deadman/remediate/transports.py`, `docs/alerting.md`,
  `tests/test_transports.py`
- AC template: gate
- Custom AC: email transport delivering through the existing ops rail; the
  out-of-band assertion runs against the **real** monitored surface list, so
  wiring the alarm to a watched rail fails at startup; repeated identical
  alerts are throttled without ever suppressing a state change; a transport
  failure is itself recorded as evidence rather than swallowed.

**DM2.8 — The board grows a memory**
- Cx: 25 · Priority: **P1** · Depends on: DM2.6
- Files: `src/deadman/board.py`, `src/deadman/service.py`,
  `tests/test_board_history.py`
- AC template: schema
- Custom AC: per surface, last observation, when it was read, which collector
  reported it, and how long it has held that state; blind and unreported
  surfaces are counted separately from healthy ones in the summary; the JSON
  contract remains backward compatible with the DM1 board.

**DM2.9 — Integration gate and the real-world proof writeup**
- Cx: 30 · Priority: **P0** · Depends on: all
- Files: `docs/PROOF.md`, `README.md`, `docs/DEMO.md`, `sample-outputs/`
- AC template: gate
- Custom AC: `docs/PROOF.md` documents the morning brief outage as a case
  study, with the evidence, the timeline, and the detection, **written from
  captured output rather than memory**; samples regenerated by script; the
  demo's break-and-heal runs against at least one real surface rather than the
  stub; full suite green, ruff clean, `arch check --strict` clean; clean clone
  reproduces.

## Dependency Graph

```
Wave 0:  DM2.1
Wave 1:  DM2.2   DM2.7            (need DM2.1)
Wave 2:  DM2.3   DM2.4            (need DM2.2)
Wave 3:  DM2.5   DM2.6            (need DM2.3 / DM2.4)
Wave 4:  DM2.8                    (needs DM2.6, serialised — see collisions)
Wave 5:  DM2.9                    (needs all)
```

## File Collision Matrix

| Wave | Tasks in parallel | Intersection |
|---|---|---|
| 1 | DM2.2, DM2.7 | **none** — `ingest/` + `service.py` vs `remediate/transports.py` |
| 2 | DM2.3, DM2.4 | **none** — `collector/` vs `verify/collector_liveness.py` |
| 3 | DM2.5, DM2.6 | **none** — `collector/surfaces.py` vs `service.py` + `infra/` |

**DM2.6 and DM2.8 both edit `src/deadman/service.py`.** Already resolved above
by making DM2.8 depend on DM2.6 rather than running beside it, which costs one
wave and removes the conflict. DM2.2 also touches `service.py` but lands two
waves earlier. Do not let engage discover this at runtime.

## Sprint Budget

- **Total Cx:** 275
- **Task count:** 9 — **P0:** 8 · **P1:** 1 · **P2:** 0
- Under DM1's 345 and inside the ~300 norm. Sized deliberately smaller because
  DM2 carries infrastructure risk DM1 did not: a new topology, a cloud service
  that has never been enabled, and a delivery rail that touches Kevin's real
  email.
- **Cut list, in order:** DM2.8 (board memory), then DM2.5's disk surface
  leaving only the morning brief. **Nothing else is cuttable.** Cutting DM2.4
  would ship a monitor whose silence is ambiguous, which is worse than shipping
  nothing.

## Integration Points

- `EvidenceStore` (DM2.1) → consumed by DM2.2, DM2.4, DM2.7, DM2.8
- Wire format (DM2.2) → consumed by DM2.3
- Collector config (DM2.3) → consumed by DM2.5
- Liveness verdicts (DM2.4) → consumed by DM2.7 and DM2.8

## Out of Scope

- **Grounding reliability.** The 1-in-4 ungrounded rate is DM3, including
  measuring it properly across 50+ live calls rather than 4.
- **The live correlation demo.** DM3.
- **Metricool and the phone relay as real surfaces.** Both need credentials and
  a destination read; the morning brief and disk need neither, and shipping two
  real surfaces beats half-shipping four.
- **Fixing `morning_brief_send.py`.** That hang is a bug in the `ops` repo.
  deadman's job is to notice it, and it already does.
- **Retiring the seven existing point-solution monitors.** Still v2, and still
  one at a time.
- **A general surface registry.** Adding a surface still means writing a probe.
