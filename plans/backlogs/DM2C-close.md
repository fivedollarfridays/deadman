# DM2C — close the sprint: board memory and the proof

**Base:** main

The two tasks the DM2 run never reached, plus what changed underneath them
since the brief was written: the service is **live and monitored for real**
now — the kevin-mac collector ships every 15 minutes, `DEADMAN_COLLECTORS`
is set, Cloud Scheduler fires the self-check, both alarms have delivered to
Kevin's inbox, and the board currently shows the real morning-brief FAULT
(185h stale via the collector) beside `collector:kevin-mac` healthy. The
captured fault fixture DM2.5 promised exists at
`tests/fixtures/real-morning-brief-fault.json`.

Target: All Things Agentic, Taskmaster category, deadline 2026-08-31 5:00pm
PDT. Judging verified from the real Devpost page: Innovation & Operational
Utility 40%, Architectural Discipline 30%, Demo & Production Readiness 30%.

**Decisions made here so tasks do not have to make them:**

1. **Collector attribution on the board is allowed as a top-level
   `reported_by` field.** It looks like it fights the DM2 redaction
   (`detail.collector_id` is withheld from the public board), but collector
   ids are already public in the liveness surface names
   (`collector:kevin-mac`), so naming the reporter reveals nothing new. The
   *detail-level* withholding stays exactly as is — `redact.py` is not
   weakened, and no absolute path, arrival stamp, or wire id becomes public.
2. **Held-duration comes from stored history, never the current sweep.** A
   duration computed from now-minus-read_at of the newest row is just a
   restatement of now. The question the board answers is "how long has this
   surface been in this state", which means walking history back to the last
   state *change*.
3. **Both tasks edit `src/deadman/service.py`, so they are serialized** —
   DM2C.2 depends on DM2C.1. Do not let engage discover this at runtime.
4. **The morning brief may heal mid-sprint.** The fix shipped in ops on
   08-11; the next 6:00am run may send, flipping the live FAULT to healthy.
   PROOF.md is written from the committed fixture and captured board output,
   not from whatever the live board says at writing time, precisely so the
   case study survives its own subject recovering.

## Phase 1: The board grows a memory

### DM2C.1 — The board grows a memory | Cx: 25 | P1

**Description:** With durable storage live, the board can answer what a single sweep cannot: how long a surface has held its state, and who reported it. Held-duration walks stored history back to the last state change rather than restating now. Blind and unreported surfaces stay counted separately from healthy ones, because folding them together is the false green this project exists against. The JSON contract stays backward compatible with the deployed DM1 board, asserted against a committed sample, since the contract already has consumers. Collector attribution rides as a top-level `reported_by` per decision 1 above; `redact.py`'s detail-level withholding is not weakened.

**AC:**
- [ ] Per surface, the board renders the last observation, when it was read, which collector reported it (`reported_by`, absent for the service's own probes), and how long it has held its current state
- [ ] Held-duration is computed from stored history back to the last state change, asserted by a test where the newest row is recent but the state is old
- [ ] A surface with a single stored row renders a held-duration without error rather than dividing by an empty history
- [ ] Blind and unreported surfaces are counted separately from healthy ones in the summary, preserved by test
- [ ] The JSON contract remains backward compatible with the DM1 board, asserted against a committed DM1 board sample
- [ ] `detail`-level redaction is unchanged: `collector_id`, `received_at`, `wire_row_id`, `reported_method` stay withheld from the public board, asserted by test
- [ ] The store-reading path is bounded: history walks use a documented limit, never an unbounded read per request
- [ ] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean, formatter before arch check

**Depends on:** None
**Model:** claude-sonnet-5

## Phase 2: Proof

### DM2C.2 — Integration gate and the real-world proof writeup | Cx: 30 | P0

**Description:** Close DM2 by proving the whole thing works together and writing the case study that is the actual argument for the project. `docs/PROOF.md` documents the morning brief outage from the committed capture (`tests/fixtures/real-morning-brief-fault.json`) and captured board output, never from memory, and states the detection latency deadman now achieves — the collector sweeps every 900s — against the seven days the real outage took to find by accident. The demo must reflect the topology that actually exists now: collector on the Mac, service on Cloud Run, scheduler firing, alarm delivering. The architecture diagram gets the collector/service split it never had. Everything regenerable is regenerated by script and enforced by test.

**AC:**
- [ ] `docs/PROOF.md` documents the morning brief outage as a case study — the evidence, the timeline, the detection — written from the committed fixture and captured output, never from memory
- [ ] The case study states the detection latency now achieved (900s collector cadence plus liveness window) against the seven days the real outage went unnoticed, and names why the outage was self-concealing
- [ ] `docs/DEMO.md` is rewritten for the real topology: collector on the Mac shipping to the live service, the board's real FAULT, the scheduler's self-check evidence, and the alarm email — with the unedited-single-take rule and the visual-proof-of-GCP requirement from the verified contest rules stated in the run sheet
- [ ] The demo's break-and-heal sequence runs against at least one real surface rather than the stub
- [ ] `sample-outputs/` is regenerated by script and enforced byte for byte by a test
- [ ] The architecture diagram shows the collector and service split, including which side of the wire each surface is read on
- [ ] `README.md` spin-up instructions reproduce from a clean clone, verified by running them verbatim
- [ ] Full suite green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean, in that order with arch check after the formatter

**Depends on:** DM2C.1
**Model:** claude-opus-5

## Delivery Summary

| ID | Title | Cx | Pri | Model | Depends on |
|---|---|---|---|---|---|
| DM2C.1 | The board grows a memory | 25 | P1 | claude-sonnet-5 | — |
| DM2C.2 | Integration gate and the real-world proof writeup | 30 | P0 | claude-opus-5 | DM2C.1 |

**Total Cx:** 55 — 2 tasks, 1 P0, 1 P1.

## Priority Order

1. DM2C.1 — the board memory DM2C.2's captured output wants on screen
2. DM2C.2 — the integration gate and the proof

## Waves

```
Wave 0:  DM2C.1
Wave 1:  DM2C.2
```

Serialized by the `service.py` collision; there is no parallelism to lose.

## Cut List

Nothing. Two tasks is the floor of a closing sprint.

## Out of Scope

- The four deferred security findings (per-collector signing, scheduler OIDC, hash-pinned constraints, recon scrub) — DM3
- The disk-trend minimum-sample floor (2 samples minutes apart currently extrapolate a 487GB/day slope) — DM3
- Grounding reliability measurement — DM3
- The rig collector — installed when it is actually installed, declared then
- Recording the demo video itself — Kevin, with the run sheet DM2C.2 produces
