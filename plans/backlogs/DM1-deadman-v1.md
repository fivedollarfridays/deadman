# DM1 — deadman v1 (contest-ready)

**Base:** main

Silent-failure detection and remediation for heterogeneous infrastructure.
Four surfaces that fail quietly and share no schema. Deterministic detection
and verification, Gemini diagnosis and remediation selection, Cloud Run deploy.

Target: All Things Agentic, Taskmaster category, deadline 2026-08-31 5:00pm PDT.
Brief: `docs/SPRINT-BRIEF-DM1.md`

Already built and out of scope as tasks: `src/deadman/evidence/model.py`,
`src/deadman/probes/base.py`, `src/deadman/probes/morning_brief.py`,
`src/deadman/probes/disk.py`.

## Phase 1: Foundation

### DM1.1 — Packaging, hermetic test suite, CI | Cx: 25 | P0

**Description:** Stand up the project so every later task has a place to land. Packaging with pinned toolchain, a socket-blocked test suite with a live canary proving the block is active, and CI running ruff plus arch check strict. This retires the "does the toolchain work" risk on day one.

**AC:**
- [ ] `pyproject.toml` declares the package with Python 3.11+ and a pinned `constraints.txt`
- [ ] `tests/conftest.py` blocks sockets for every test with an `allow_network` marker as the only escape hatch
- [ ] `tests/test_suite_is_hermetic.py` makes a real outbound call and asserts it is blocked
- [ ] A second canary test asserts the `allow_network` marker still permits real socket errors through
- [ ] `.github/workflows/ci.yml` runs pytest, `ruff check`, and `bpsai-pair arch check --strict`
- [ ] CI is green on the branch before this task closes
- [ ] `.gitignore` excludes history artifacts, venvs, and build output

**Depends on:** None
**Model:** claude-sonnet-5

## Phase 2: Prove the contract

### DM1.2 — Tests for the evidence model and probe contract | Cx: 20 | P0

**Description:** Lock the two ideas the whole system rests on. Absence is a distinct state from failure, and evidence carries how it was obtained. These tests are the guardrail against the failure mode already observed in a sibling project, where a swallowed HTTP error surfaced as a data verdict.

**AC:**
- [ ] A probe that raises yields `Observation.UNOBSERVABLE`, never `FAULT`
- [ ] A probe returning a non-`Evidence` value is contained and yields `UNOBSERVABLE`
- [ ] `blind_spots()` returns unobserved surfaces and excludes healthy ones
- [ ] `Method` trust ordering asserts `DESTINATION_API` outranks `REPORTED`
- [ ] `Evidence.provenance_row()` returns source, method, surface, and an ISO timestamp
- [ ] `unobservable()` records the reason in `detail`
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.1
**Model:** claude-sonnet-5

### DM1.3 — Tests for the morning brief and disk probes | Cx: 20 | P0

**Description:** Cover the two probes already written, with emphasis on the distinctions that make them correct rather than merely working. The brief probe must never trust file mtime, and the disk probe must fire on a healthy level with a bad trend.

**AC:**
- [ ] Brief probe: missing log inside an existing directory yields `FAULT`
- [ ] Brief probe: missing parent directory yields `UNOBSERVABLE`, not `FAULT`
- [ ] Brief probe: a file whose mtime is fresh but whose last row is stale still yields `FAULT`
- [ ] Brief probe: a torn final row falls back to the newest parseable row
- [ ] Brief probe: a future-dated timestamp yields `UNOBSERVABLE`
- [ ] Disk probe: ample free space with a shrinking slope inside the runway window yields `FAULT`
- [ ] Disk probe: a single sample yields `HEALTHY` and reports no trend
- [ ] Disk probe: one outlier sample does not flip the projection
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.1
**Model:** claude-sonnet-5

## Phase 3: Surfaces and platform

### DM1.4 — Metricool probe and destination-verification spike | Cx: 35 | P1

**Description:** The surface with a real incident behind it: a scheduled post reported published and never appeared, uncaught. Open with a spike establishing whether the destination platform is readable at all, because Meta approval appears unavailable and that decides the evidence tier this probe can honestly claim.

**AC:**
- [ ] `docs/metricool-verification.md` records whether the platform is readable via API, public permalink, or neither
- [ ] The chosen verification path is expressed as a `Method` and the resulting trust tier is documented
- [ ] Scheduler-reported success alone never yields `HEALTHY`
- [ ] A post reported published but absent at the destination yields `FAULT` naming the post id
- [ ] An unreachable destination yields `UNOBSERVABLE`, never `FAULT`
- [ ] Tests cover published, missing, and unreachable with no live network calls
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.1
**Model:** claude-opus-5

### DM1.8 — Cloud Run deployment via Cloud Build | Cx: 30 | P0

**Description:** Satisfy the contest requirement for at least one Google Cloud infrastructure service with visible proof it runs there. Build through Cloud Build specifically so no local Docker daemon is required.

**AC:**
- [ ] `Dockerfile` builds the service image
- [ ] `cloudbuild.yaml` builds and pushes without a local Docker daemon
- [ ] Service deploys to Cloud Run and returns the current board at a reachable endpoint
- [ ] `infra/README.md` documents project setup, required APIs, and the deploy command
- [ ] A fresh clone can reach a deployed URL following only that README
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.1
**Model:** claude-sonnet-5

### DM1.9 — Phone and SMS relay probe with active canary | Cx: 30 | P1

**Description:** The surface where passive observation is genuinely ambiguous. Silence means either no traffic or a dead rail and those look identical, so this probe manufactures its own evidence rather than inferring health from quiet.

**AC:**
- [ ] Silence without a canary yields `UNOBSERVABLE`, never `HEALTHY`
- [ ] The canary send is verified at the destination sent folder, not at dispatch
- [ ] An unreachable host is distinguished from a rejected send in the evidence detail
- [ ] Canary cadence is configurable and defaults to conservative
- [ ] Tests cover reachable, unreachable, and send-rejected with no live network calls
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.1
**Model:** claude-sonnet-5

## Phase 4: The brain

### DM1.5 — Diagnosis layer on Gemini via ADK | Cx: 40 | P0

**Description:** Where the model earns its place. Detection is deterministic; diagnosis is inferential. This layer reads heterogeneous unstructured failure evidence and forms a causal hypothesis, which is the thing rule engines cannot do and the reason this is an agent rather than a cron job.

**AC:**
- [ ] Consumes unstructured `Evidence.detail` and emits a typed `Diagnosis`
- [ ] `Diagnosis` carries hypothesis, confidence, and the evidence ids it rests on
- [ ] A test plants a fabricated claim in the model response and asserts it is rejected
- [ ] The model is never permitted to assert a fact absent from the supplied evidence
- [ ] Tests run offline against recorded responses with no live API calls
- [ ] Model, temperature, and prompt version are recorded on every diagnosis
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.1, DM1.2
**Model:** claude-opus-5

### DM1.11 — Self-liveness and out-of-band alerting | Cx: 25 | P1

**Description:** The monitor must prove its own liveness from capture evidence it wrote, and its alarms must not travel through anything it watches. A sibling system ran dead for nine days precisely because the failing surface was also the alerting channel.

**AC:**
- [ ] `self_check` exits non-zero when the newest self-written evidence is older than the window
- [ ] `self_check` exits non-zero when there is no self-written evidence at all
- [ ] Alert transport is asserted at configuration time to not be a monitored surface
- [ ] A monitored surface configured as the alert channel raises at startup
- [ ] Tests cover live, stale, and no-evidence cases
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.8
**Model:** claude-sonnet-5

## Phase 5: Action

### DM1.6 — Remediation registry and executor | Cx: 35 | P0

**Description:** The Taskmaster requirement. Selection is a function of the diagnosis rather than the fault, because re-queueing a post that failed on an expired token fails identically, and re-queueing one rejected on policy is worse than doing nothing. Actions themselves are deterministic code, never model output.

**AC:**
- [ ] Action selection keys on the diagnosis, not the fault class
- [ ] An expired-credential diagnosis does not select a retry action
- [ ] A transient 5xx diagnosis does select an immediate retry
- [ ] Every action is deterministic code; no action body is generated at runtime
- [ ] A diagnosis with no matching action escalates rather than guessing
- [ ] Dry-run mode executes selection and reports the plan without side effects
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.5
**Model:** claude-opus-5

### DM1.10 — Cross-surface correlation | Cx: 30 | P1

**Description:** The differentiator against graph-based monitoring. No lineage graph exists across a disk, a phone relay and a scheduler, so a shared root cause must be inferred from co-occurrence and evidence rather than traversed. Inferring the graph is harder than walking a given one.

**AC:**
- [ ] Concurrent faults across surfaces are offered as one incident with a hypothesised shared cause
- [ ] The report states the relationship was inferred, not traversed
- [ ] A single isolated fault never produces a correlation
- [ ] Correlation confidence is carried and surfaced, never implied
- [ ] Tests cover the disk-fills-then-everything-dies case using recorded evidence
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.3, DM1.5
**Model:** claude-opus-5

### DM1.7 — Verification loop | Cx: 25 | P0

**Description:** Closes the honesty gap. A remediation that reports success without re-observing the surface is just another heartbeat, which is the thing this project argues against. Success means a fresh healthy observation, not an executor return value.

**AC:**
- [ ] The originating probe is re-run after remediation
- [ ] Success requires a fresh `HEALTHY` observation from that probe
- [ ] The executor's own return value is never sufficient to declare success
- [ ] A fix that cannot be re-observed is reported unverified, not successful
- [ ] Repeated failed remediation stops rather than looping
- [ ] `ruff check` clean on touched files

**Depends on:** DM1.6
**Model:** claude-sonnet-5

## Phase 6: Ship

### DM1.12 — Integration gate: demo, README, architecture diagram | Cx: 30 | P0

**Description:** The contest scores demo and production readiness at thirty percent and requires a live unedited demo. Rehearse a break-and-heal sequence end to end, commit real sample outputs generated by script, and verify a clean clone reproduces.

**AC:**
- [ ] `docs/DEMO.md` scripts a break-and-heal sequence runnable in one unedited take
- [ ] The sequence has been rehearsed end to end at least once and the runtime recorded
- [ ] `sample-outputs/` is regenerated by a committed script, never hand-written
- [ ] `docs/architecture.png` shows the deterministic and inferential layers distinctly
- [ ] README opens with what it is and why it differs, not with installation
- [ ] Full suite green, `ruff check` clean, `bpsai-pair arch check --strict` clean
- [ ] A clean clone reproduces setup following only the README

**Depends on:** DM1.1, DM1.2, DM1.3, DM1.4, DM1.5, DM1.6, DM1.7, DM1.8, DM1.9, DM1.10, DM1.11
**Model:** claude-sonnet-5

## Delivery Summary

| ID | Title | Cx | Pri | Depends on | Model |
|---|---|---|---|---|---|
| DM1.1 | Packaging, hermetic tests, CI | 25 | P0 | None | claude-sonnet-5 |
| DM1.2 | Evidence model and probe contract tests | 20 | P0 | DM1.1 | claude-sonnet-5 |
| DM1.3 | Brief and disk probe tests | 20 | P0 | DM1.1 | claude-sonnet-5 |
| DM1.4 | Metricool probe and spike | 35 | P1 | DM1.1 | claude-opus-5 |
| DM1.5 | Diagnosis on Gemini via ADK | 40 | P0 | DM1.1, DM1.2 | claude-opus-5 |
| DM1.6 | Remediation registry and executor | 35 | P0 | DM1.5 | claude-opus-5 |
| DM1.7 | Verification loop | 25 | P0 | DM1.6 | claude-sonnet-5 |
| DM1.8 | Cloud Run via Cloud Build | 30 | P0 | DM1.1 | claude-sonnet-5 |
| DM1.9 | SMS relay probe with canary | 30 | P1 | DM1.1 | claude-sonnet-5 |
| DM1.10 | Cross-surface correlation | 30 | P1 | DM1.3, DM1.5 | claude-opus-5 |
| DM1.11 | Self-liveness and out-of-band alerting | 25 | P1 | DM1.8 | claude-sonnet-5 |
| DM1.12 | Integration gate | 30 | P0 | all | claude-sonnet-5 |

**Total Cx:** 345 across 12 tasks. P0: 8, P1: 4, P2: 0.

## Priority Order

1. DM1.1 — nothing else can start
2. DM1.8 — contest eligibility depends on a GCP service, retire that risk early
3. DM1.2, DM1.3 — lock the contract before building on it
4. DM1.5 — the Gemini requirement and the brain
5. DM1.6 — the Taskmaster requirement, the agent must act
6. DM1.7 — without it, remediation is unproven
7. DM1.12 — the demo is thirty percent of the score
8. DM1.4 — best surface, has a real incident behind it
9. DM1.9 — the ambiguity case
10. DM1.11 — self-liveness
11. DM1.10 — first to cut if budget overflows

**Cut list if over budget, in order:** DM1.10, DM1.9, DM1.11, DM1.4.
