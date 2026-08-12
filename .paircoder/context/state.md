# Current State

> Last updated: 2026-08-12

<!-- paircoder:state:begin -->
## Active Plan

**Plan:** `plan-2026-08-dm2c-close` — DM2C: close the sprint
**Status:** Complete — 2 of 2 `done`; branch `engage/dm2c-close` ready to merge
**Current Sprint:** DM2C
**Backlog:** `plans/backlogs/DM2C-close.md`
**Branch:** `engage/dm2c-close`

**Previous sprints:** `plan-2026-08-dm2-make-it-real` — DM2, 7 of 9 `done`,
merged and deployed (DM2.8/DM2.9 were never reached and are superseded by
DM2C.1/DM2C.2). `plan-2026-08-dm1-deadman-v1` — DM1, 12 of 12 `done`,
merged. Live at https://deadman-mrapac5nda-uc.a.run.app.

Silent-failure detection and remediation for heterogeneous infrastructure.
Submission target: All Things Agentic, Taskmaster category, **deadline
2026-08-31 5:00pm PDT**.

## Current Focus

**DM1 built a monitor that has never monitored anything.** It is a library, a
test suite, and an endpoint that sweeps when a human sends it a GET. Nothing
runs on a cadence, nothing survives a cold start, and zero surfaces watch real
infrastructure. DM2 makes it real.

**The finding that justifies the sprint.** Pointing the existing
`MorningBriefProbe` at `~/ops/data/brief-send-log.jsonl` with no new code
returned FAULT immediately: no brief sent since 2026-08-04 06:56. Seven days,
undetected, because the brief is itself the alerting channel and a dead brief
cannot report its own death. That is the doctrine's canonical failure, live, in
the estate this was built for.

**The central architectural fact.** The surfaces are not where the service is.
Cloud Run cannot read a log on the Mac, and opening inbound access to a laptop
is the wrong answer. So DM2 splits into a **collector** that runs where the
surfaces live and ships evidence to an authenticated ingest endpoint, and the
hosted **service** that stores, correlates and alerts. This is a topology
change, not a config change, and it drives the dependency graph.

**Two commitments that constrain every task.** `pyproject.toml` declares
`dependencies = []` — every new backend follows the `GeminiClient` seam
(optional extra plus SDK imported inside the constructor). And evidence
crossing a wire changes its provenance: the service receives a *report of* a
local reading, and silently upgrading the method on arrival reintroduces the
heartbeat this project exists to argue against.

### Carried forward from DM1

**The service is live and public** at https://deadman-mrapac5nda-uc.a.run.app
(project `deadman-20260810`). `GET /` returns the board. DM2.6 redeploys it.

**Contest eligibility is no longer at risk.** The live Gemini call has now
happened: `gemini-3.5-flash` through the ADK, returning a structured
`Diagnosis` with citations. That was the single largest open risk, since an
untested call shape is not a quality problem but a disqualification. See
`docs/gemini-verification.md`.

**Spike result that changes the demo:** Instagram and Facebook destinations are
unreadable, so the Metricool surface is a declared permanent blind spot for
Instagram. X is verifiable. See `docs/metricool-verification.md`.

## Task Status

### Active Sprint (DM2C) — 2 tasks, 55 Cx, 1 P0 + 1 P1, 2 `done`

| ID | Title | Pri | Cx | Model | Depends on |
|---|---|---|---|---|---|
| DM2C.1 | The board grows a memory ✓ | P1 | 25 | claude-sonnet-5 | — |
| DM2C.2 | Integration gate and the real-world proof writeup ✓ | P0 | 30 | claude-opus-5 | DM2C.1 |

**Waves:** `DM2C.1` → `DM2C.2` — serialized by design (backlog decision 3):
both tasks edit `src/deadman/service.py`'s output surface, so the dependency
is declared up front rather than discovered by engage at runtime.

**Cut list:** nothing — two tasks is the floor of a closing sprint.

**Decisions pre-made by the backlog** (tasks do not re-litigate): (1)
collector attribution is a top-level `reported_by`, detail-level redaction
untouched; (2) held-duration walks stored history to the last state change,
never now-minus-newest-read_at; (4) PROOF.md is written from the committed
fixture and captured board output because the live FAULT may heal mid-sprint.

### Previous Sprint (DM2) — 9 tasks, 275 Cx, 7 `done`, DM2.8/DM2.9 superseded by DM2C

| ID | Title | Pri | Cx | Model | Depends on |
|---|---|---|---|---|---|
| DM2.1 | Evidence store: Protocol seam + durable backend ✓ | P0 | 35 | claude-opus-5 | — |
| DM2.2 | Authenticated ingest, and what a reported observation means ✓ | P0 | 35 | claude-opus-5 | DM2.1 |
| DM2.7 | An alarm that actually reaches Kevin ✓ | P0 | 30 | claude-sonnet-5 | DM2.1 |
| DM2.3 | The collector: sweep where the surfaces actually are ✓ | P0 | 35 | claude-sonnet-5 | DM2.2 |
| DM2.4 | Collector liveness: absence must not read as health ✓ | P0 | 30 | claude-opus-5 | DM2.2 |
| DM2.5 | Real surfaces, starting with the one already broken ✓ | P0 | 30 | claude-sonnet-5 | DM2.3 |
| DM2.6 | Scheduled sweeps and scheduled self-check ✓ | P0 | 25 | claude-sonnet-5 | DM2.4 |
| DM2.8 | The board grows a memory — superseded by DM2C.1 | P1 | 25 | claude-sonnet-5 | DM2.6 |
| DM2.9 | Integration gate and the real-world proof writeup — superseded by DM2C.2 | P0 | 30 | claude-opus-5 | all |

**Waves:** `DM2.1` → `DM2.2 DM2.7` → `DM2.3 DM2.4` → `DM2.5 DM2.6` →
`DM2.8` → `DM2.9`

**File collisions:** none inside a wave. DM2.6 and DM2.8 both edit
`service.py`, resolved by making DM2.8 depend on DM2.6 — costs one wave,
removes the conflict.

**Cut list, in order:** DM2.8, then DM2.5's disk surfaces leaving only the
morning brief. **Nothing else is cuttable.** Cutting DM2.4 would ship a
monitor whose silence is ambiguous, which is worse than shipping nothing.

**Privileged:** DM2.6 touches live billable cloud infrastructure
(`deadman-20260810`). DM2.7 sends one real email over the ops rail.

### Previous Sprint (DM1) — 12 tasks, 345 Cx, all 12 `done`

| ID | Title | Pri | Cx | Model | Depends on |
|---|---|---|---|---|---|
| DM1.1 | Packaging, hermetic test suite, CI ✓ | P0 | 25 | claude-sonnet-5 | — |
| DM1.2 | Evidence model + probe contract tests ✓ | P0 | 20 | claude-sonnet-5 | DM1.1 |
| DM1.3 | Brief + disk probe tests ✓ | P0 | 20 | claude-sonnet-5 | DM1.1 |
| DM1.4 | Metricool probe + verification spike ✓ | P1 | 35 | claude-opus-5 | DM1.1 |
| DM1.5 | Diagnosis layer on Gemini via ADK ✓ | P0 | 40 | claude-opus-5 | DM1.1, DM1.2 |
| DM1.6 | Remediation registry and executor ✓ | P0 | 35 | claude-opus-5 | DM1.5 |
| DM1.7 | Verification loop ✓ | P0 | 25 | claude-sonnet-5 | DM1.6 |
| DM1.8 | Cloud Run via Cloud Build ✓ | P0 | 30 | claude-sonnet-5 | DM1.1 |
| DM1.9 | SMS relay probe with active canary ✓ | P1 | 30 | claude-sonnet-5 | DM1.1 |
| DM1.10 | Cross-surface correlation ✓ | P1 | 30 | claude-opus-5 | DM1.3, DM1.5 |
| DM1.11 | Self-liveness + out-of-band alerting ✓ | P1 | 25 | claude-sonnet-5 | DM1.8 |
| DM1.12 | Integration gate: demo, README, diagram ✓ | P0 | 30 | claude-opus-5 | all |

**Waves:** `DM1.1` → `DM1.2 DM1.3 DM1.4 DM1.8 DM1.9` → `DM1.5 DM1.11` →
`DM1.6 DM1.10` → `DM1.7` → `DM1.12`

**Cut list if over budget, in order:** DM1.10, DM1.9, DM1.11, DM1.4.

### Backlog

Out of scope for DM2 (DM3 or later): grounding reliability and the 1-in-4
ungrounded rate measured across 50+ live calls; the live correlation demo;
Metricool and the phone relay as real surfaces (both need credentials and a
destination read); fixing `morning_brief_send.py`, which is an `ops` repo bug
— deadman's job is to notice it, and it already does; retiring the seven
existing point-solution monitors; a general surface registry.

## What Was Just Done

### Session: 2026-08-12 — DM2C.2 done: the proof, the run sheet, and a demo stage with nothing standing in

**DM2C closes. Both tasks `done`, all eight DM2C.2 ACs checked.**

**`docs/PROOF.md` is the case study, and it is enforced.** The morning brief
outage written from two committed captures and never from memory: the DM2.5
probe capture (`FAULT`, 176.7h, last send 2026-08-04T11:56:45) and a **new
board capture** — `GET /` off the deployed service, taken this session at
2026-08-12T05:42:43Z while the outage was still live. `tests/test_proof_doc.py`
asserts every duration and every timestamp in the prose is findable in one of
the two captures, so prose that drifts from the evidence fails the suite.

**The board capture is the wire made visible in output.** The same surface
appears twice: `cron:morning-brief` `FAULT` at 185.7h via the kevin-mac
collector with `method: reported` (downgraded on arrival), and
`cron:morning-brief` `UNOBSERVABLE` from Cloud Run, which has no such log —
listed under `blind_spots`, never counted healthy. `collector:kevin-mac` sits
beside them healthy inside its 1800s deadline, which is what makes the fault
worth believing. Captured deliberately off the deployed revision (`86c3662`),
which predates DM2C.1, so no row carries `reported_by`/`held_since` and PROOF
says so rather than describing fields the capture does not have.

**The detection latency, stated as arithmetic:** 30h of deliberate probe
tolerance plus at most one 900s sweep, with the 1800s collector-silence
deadline as the term that makes the claim mean anything — against 176.7h found
by accident.

**The demo now breaks a real surface first.** New stage 1
(`scripts/demo_real_surface.py`): a real `MorningBriefProbe` over a real file,
no client and no seam. The break is the outage's own last log row read out of
the committed capture; detection is off the real clock; the `UNKNOWN` cause
escalates out of band (no shipped action fixes a hung cron job, and inventing
one is the guess the design forbids); the heal is the write a repaired brief
job makes, proved by a fresh observation. The relay stub stays for the
*automated* act-and-verify path and is still named out loud. Nine stages now.

**`docs/DEMO.md` is a run sheet for the topology that exists** — pre-flight
(every command executed and corrected against this Mac), seven beats, the
failure playbook. The unedited-single-take rule and the visual-proof-of-GCP
requirement are stated up front with their provenance named. **Caveat worth
carrying:** no network verification of the rules page was available from this
session (WebSearch/WebFetch not permitted), so the sheet cites the recorded
Devpost reading in `plans/backlogs/DM2C-close.md` and instructs Kevin to
re-read the rules immediately before recording.

**The diagram grows the split it never had.** `docs/architecture.svg` has a
topology band — Mac collector (900s, spool, `local_artifact`), the wire
(`POST /evidence`, signed, capped at `reported`), Cloud Run (what it reads
itself, and the surface it cannot). `tests/test_architecture_diagram.py`
asserts each surface sits in the correct panel group, so the picture cannot
quietly go stale again.

**Two defects found by verifying rather than asserting:**

1. `python scripts/generate_samples.py` **failed from a plain shell.**
   `deadman.service` builds its app at import and fails closed without the
   ingest/scheduler secrets, which `conftest` supplied and a bare shell did
   not — so the documented regeneration command worked only inside pytest. A
   regeneration step nobody can run is a hand-written sample with extra steps.
   Fixed in the generator, pinned by a subprocess test with every `DEADMAN_*`
   variable stripped.
2. `infra/scheduler.md` still said steps 1–3 were **"not yet executed"**.
   DM2.6 executed them. The section now records the verification and adds a
   cheaper check anyone can run without `gcloud`: `undeclared_surfaces`
   containing `self:sweep` is the store confirming it holds self-check
   evidence.

**Verification, in order:** `pytest -n auto --dist=worksteal` 609 passed;
`ruff check .` clean; `ruff format --check .` 178 files; `bpsai-pair arch check
--strict` no violations. Clean-clone check run verbatim in two fresh temp dirs
— `main` from GitHub (573 passed) and this branch (609 passed), plus the demo,
sample regeneration (byte-identical) and `deadman-self-check` in the fresh
clone.

**Kevin still owes:** the demo video recording (the run sheet is ready), the
Devpost submission, repo sharing with the judge addresses — and the repo is
still private.

### Session: 2026-08-12 — DM2C.1 done: the board grows a memory

**Every board row now says how long it has held its state and who reported
it.** `src/deadman/board.py` is new: `held_since` walks a surface's stored
history newest-to-oldest until the observation changes, so a FAULT that has
been re-confirmed every few minutes for three days reports `held_since` at
the three-day mark, not the five-minutes-ago mark of its newest reading —
`tests/test_board_memory.py::TestHeldDuration::test_held_since_walks_back_to_the_last_state_change`
pins exactly that shape. No division anywhere in it, so a single-row surface
(or one with no store at all — the plain local-sweep case) falls back to
its own `read_at` and renders a zero duration rather than raising or
indexing into history that isn't there.

**`reported_by` is a deliberate, narrow exception to `redact.py`'s gate, not
a loosening of it.** It is gated on `detail['received_at']` rather than
`detail['collector_id']` alone: a liveness verdict the service derives
itself (a collector's own liveness row, a surface judged stale or never
reported) also carries `collector_id` — naming which collector the row
*concerns* — but only a row that actually crossed the wire through
`ingest.arrival.on_arrival` sets `received_at`. Getting that gate right
mattered: the naive version (any row with `collector_id`) would have put
`reported_by` on the collector's own synthesized liveness row too, which is
backwards.

**That gate collided with an existing pinned test, and the collision was
real, not just a state.md prediction.** Planning's note said
`test_collector_identity_is_withheld` would "pass unmodified"; it didn't —
adding `reported_by: "mac-mini"` to a row necessarily puts `"mac-mini"` back
into `str(published)`, which the old assertion checked directly. Renamed to
`test_collector_identity_is_withheld_from_detail` and narrowed to check
`detail` specifically (the thing the AC actually promises stays withheld),
paired with a new `TestCollectorAttributionIsADeliberateTopLevelField`
asserting both sides: `reported_by` public, `detail['collector_id']` still
gone. Worth remembering: a planning-time prediction about which tests stay
green is a hypothesis, not a constraint — the AC checklist (detail-level
redaction unchanged) was the actual contract, and it held.

**The DM1 board's JSON contract is now pinned by a real compatibility test,
not just the byte-identical generator check.** `tests/fixtures/dm1-board-sample.json`
is `sample-outputs/board.json` exactly as committed at the DM1 merge
(`git show ef40500:sample-outputs/board.json`), frozen rather than
regenerated. `tests/test_board_dm1_contract.py` asserts every key DM1 ever
promised — top-level, per-row, and per-detail — is still present on a board
built today. `test_sample_outputs.py`'s byte-for-byte check was the wrong
tool for this question: it fails the moment the board legitimately grows a
field, which is exactly what this task does.

**Hit both of the architecture caps state.md flagged during planning, in
one edit.** Adding `held_since`/`reported_by`/`history_for` inline in
`service.py` tripped both "too many imports" (21 > 20) and "too many
functions" (17 > 15) simultaneously. Fixed the way DM2's own
`verify/surface_verdict.py` split was fixed: pulled the three helpers into
a new `src/deadman/board.py`, which net *removed* two import statements
from `service.py` (the ones only those helpers needed) while adding back
only one (for the new module) — 18 statements, comfortably under the cap,
and `service.py`'s own function count back to its pre-task 14.

**`store` now threads through `build_board` → `make_app` → `build_app`**,
read per request like `probes_fn`/`liveness_fn` already were, and bounded:
`board.history_for` always calls `store.history(surface, limit=DEFAULT_HISTORY_LIMIT)`,
never an unbounded read — `tests/test_board_memory.py::TestHistoryReadIsBounded`
spies on the actual limit passed. `scripts/generate_samples.py` needed one
line (`row["held_since"] = NOW.isoformat()`) alongside its existing
`read_at` fix-up, since the un-stored sample probes' `held_since` otherwise
carried real wall-clock generation time and broke the generator's own
determinism test.

All 8 ACs checked in `.paircoder/tasks/DM2C.1.task.md` with evidence. Gates:
`pytest -n auto --dist=worksteal` 586/586 (up from 573), `ruff check .` and
`ruff format --check .` clean, `bpsai-pair arch check --strict` clean,
`sample-outputs/board.json` regenerated (additive `held_since`/`held_seconds`
per row, diff reviewed).

### Session: 2026-08-12 — DM2C planned (`/pc-plan DM2C-close.md`)

Materialized 2 task files under `.paircoder/tasks/` from
`plans/backlogs/DM2C-close.md` and registered both against the existing
`plan-2026-08-dm2c-close` (which engage had created with zero tasks —
`bpsai-pair status` was reporting both task files as not found, same shape
as the DM2 planning session).

**The task files are anchored to code, not restated from the backlog.** An
explore pass surfaced three facts the implementation plans now carry:

- **`build_board` (`service.py:106`) never touches the store** — it takes
  probes plus a pre-computed `LivenessReport`; the store lives only in
  `build_app` (:363). Held-duration needs `store.history()`, so DM2C.1's
  plan threads an optional `store` param into board assembly rather than
  computing duration in the liveness layer, which would cover only
  collector-reported surfaces. `EvidenceStore.history` already exists with
  `DEFAULT_HISTORY_LIMIT = 50`, oldest-first — DM2.1 built that seam for
  precisely this task, so the bounded-read AC is met by using it, not by
  new store surface.
- **`reported_by` collides head-on with `redact.WITHHELD_DETAIL_KEYS`**
  (`redact.py:35`) and its pin
  `test_security_hardening.py::test_collector_identity_is_withheld`. Backlog
  decision 1 already rules on this (collector ids are public in liveness
  surface names, so a top-level derived `reported_by` reveals nothing new);
  the task file demands the existing withholding test keep passing
  *unmodified* plus a new paired test asserting both sides of the boundary.
- **There is no DM1 board-compat test to lean on.** `test_sample_outputs.py`
  is a byte-for-byte change-detector that will correctly *fail* when the row
  shape grows. DM2C.1 therefore commits a DM1-era board sample (extractable
  via `git show <dm1-merge>:sample-outputs/board.json`) and writes a real
  additive-evolution contract test against it.

Also corrected while planning: the backlog's "200-line arch cap" phrasing —
`service.py` is already 384 lines; the enforced caps are 50 lines per
function and the ~20-import threshold (DM2.6 tripped `21 > 20`), both via
`arch check --strict`. The task file budgets against the real gates.

**Model assignments follow the backlog** (DM2C.1 `claude-sonnet-5`, DM2C.2
`claude-opus-5`), same rationale as the DM2 planning session: `calibration
recommend-model` returns doctrine picks flagged `insufficient_samples`
(sonnet-5 plain, opus-4-8 cross-module), and the backlog matches the repo's
own opus-for-seam-defining convention.

PM provider is `none` (Trello not connected), so local-only: no sync step.
`bpsai-pair validate` passes; budget check ~18.5k tokens per task (<2%),
well under the 75% threshold. Wave order `DM2C.1 → DM2C.2`, serialized by
the declared `service.py` collision (backlog decision 3).

### Session: 2026-08-12 — the collector is real: DM2.7 closed, kevin-mac installed and watched

**The estate is now actually monitored.** The full loop DM2 was designed for
ran for the first time: a collector on Kevin's Mac swept real surfaces,
signed a batch, shipped it to the live service, the rows landed in Firestore,
and the board reports both the evidence and the collector's own liveness.

**DM2.7 closed.** The "DUMMY SMTP" label the build agent read was stale — the
rail works, proven behaviorally rather than by reading `.env` (the morning
brief delivered through it until 08-04). Two real messages confirmed received
in Kevin's inbox: one through `ops/lib/email_send.py`, one through
**deadman's own `EmailTransport`** with ops `SMTP_*` mapped to
`DEADMAN_ALERT_*`. The out-of-band assertion ran against the real monitored
surface list and passed. All nine DM2.7 ACs now checked.

**The kevin-mac collector is installed**, per the hardened runbook:
`~/.deadman` (700) with `collector-env.sh` (600, secret piped from Secret
Manager over ssh and never printed), config at `~/.deadman/collector.json`
(spool and disk history under `~/.deadman/`, durable across reboot, rather
than the example's `/tmp`), plist materialized, `plutil -lint` gated,
`launchctl bootstrap`ed, RunAtLoad exit 0, 900s cadence. Dry-run first, then
a real run: batch accepted, spool empty, both surfaces in Firestore.

**And the service watches its silence.** `infra/collector/collectors.json`
(kevin-mac only — declaring the uninstalled rig collector would be a FAULT
the board correctly reports forever) rides in the image via a Dockerfile
COPY; `DEADMAN_COLLECTORS=/app/infra/collector/collectors.json` set on the
service. Deployed at tag `86c3662`.

**The live board now shows** (`GET /`): `collector:kevin-mac` healthy inside
its 1800s deadline; `cron:morning-brief` **FAULT via the collector** — "no
brief sent in 185.0h (~7 missed)", the real outage watched by real
infrastructure, method correctly downgraded to `reported` on arrival; and
`host:mac/disk` FAULT on the day's real disk crisis. Known behavior worth a
DM3 look: the disk slope extrapolates from 2 samples minutes apart
(487GB/day), so young trends over-alarm until history accumulates.

**Also found this session:** the venv had no `pip` (uv-built), so the new
`deadman-collector` entry point needed `uv pip install -e . --python
.venv/bin/python` — `deadman-self-check` existing while `deadman-collector`
404s is the symptom.

**Remaining in DM2: DM2.8 (board memory) and DM2.9 (integration gate +
PROOF.md).** Kevin still owes: the demo video recording, the Devpost
submission, and repo sharing with the judge addresses.

### Session: 2026-08-11 — DM2.6 verified end to end, budget alert set

**DM2.6 is no longer blocked. The scheduler fired and the evidence landed.**
`cloudscheduler.googleapis.com` enabled, job `deadman-self-check` created in
`us-central1` on `*/15 * * * *` against `${URL}/self-check`, bearer token read
from Secret Manager.

Verified the way `infra/scheduler.md` insists on, because a job's own status is
not evidence. The job attempted at `04:40:16Z`, and the row read back out of
Firestore is:

```
observation healthy · method local_artifact · read_at 2026-08-12T04:40:16Z
summary "scheduled self-check: sweep completed (2 surfaces, 1 blind)"
detail keys: blind, sweep_size
```

That is the cold-start claim proven against the real deploy rather than
in-process: the scheduler fired, the request reached the authenticated
endpoint, the endpoint swept, and the write landed in Firestore where a
different instance can read it back.

**Two path traps found while doing it**, both worth knowing because each
produces a confident wrong answer:

- The endpoint is `/self-check`, **not** `/scheduled/self-check`. The wrong
  path returns `405`, which reads like "route exists, wrong method" and would
  have produced a scheduler job failing silently forever. `SCHEDULED_PATH` in
  `src/deadman/scheduled/endpoint.py` is the authority.
- Firestore document ids are **already** percent-encoded by `surface_key`, so
  `self:sweep` is stored as the literal `self%3Asweep`. Reading it over the
  REST API needs `self%253Asweep`; the single-encoded form returns an empty
  collection rather than an error, which looks exactly like "nothing was
  written".

**The `$25` budget alert is set** on billing account `0148CA-176C18-47F84E`,
scoped to this project, with alerts at 50%, 90% and 100% of current spend
(budget id `647bb862-1d00-4c9f-8cdb-ac264f8cf766`). It had been unset since
the project was created, which mattered more once Firestore started taking
writes.

**Still carrying the deferred finding #4:** the bearer token lives in the
Cloud Scheduler job resource, readable by any principal with
`cloudscheduler.jobs.get`. Replacing it with OIDC needs the endpoint to accept
Google-signed tokens, which is a code change, so it stays DM3.

### Session: 2026-08-11 — DM2 IS LIVE, and deploying it found a bug nothing else could

**The service now runs DM2**, image tag `6d6ad33`, matching `main` exactly,
revision `deadman-00010-t6g`, at https://deadman-mrapac5nda-uc.a.run.app.

**Correction to the previous entry: `gcloud` was never missing.** It is at
`/home/kmasty/google-cloud-sdk/bin/gcloud` on the rig, already authenticated as
`kmasty1@gmail.com` against `deadman-20260810`. It is simply not on the PATH a
non-interactive `ssh` gets, so `command -v gcloud` reported nothing. The earlier
"gcloud is on neither machine" claim was wrong.

**Deploying DM2 required three things that did not exist**, each of which would
have crash-looped the service on its own:

1. **Firestore was never enabled** and had no database. `cloudbuild.yaml` sets
   `DEADMAN_STORE_BACKEND=firestore` and the backend raises at construction.
   Enabled, database created at `nam5` per `infra/README.md`, whose runbook was
   correct.
2. **Neither secret was set on the service.** DM1 needed none; DM2 refuses to
   start without both. Created in Secret Manager, `roles/secretmanager.
   secretAccessor` bound to the runtime account, and attached to the *existing*
   revision first so DM2 landed into an environment that already satisfied its
   startup check.
3. `roles/datastore.user` for the Cloud Run runtime account.

**The bug the deploy found: every `POST /evidence` hung until Cloud Run
returned 504 after five minutes.** `GET /` was fine. `_read_body` asked the
socket for `MAX_BODY_BYTES + 1` regardless of `Content-Length`, and
`wsgiref.simple_server` hands over the raw socket file object, so it blocked
waiting for 256 KiB the client never sent. **The one endpoint this whole sprint
exists to add was unusable over real HTTP**, and 568 tests plus a 13-finding
security audit all missed it, because every in-process test builds `environ`
around an `io.BytesIO` — a stream that cannot block cannot reproduce a block.
Fixed and merged (PR #9); `tests/test_ingest_body_read.py` asserts the
*requested size* rather than the bytes returned, which is the thing that
differs between a BytesIO and a socket.

**Verified against the running service, not the build's SUCCESS:**

- `GET /` 200 in 0.06s, and **the redaction is live**: the board shows
  `"withheld": ["path"]` and `"source": "morning-brief.jsonl"` rather than the
  absolute path. Zero occurrences of `/Users/`, `/home/` or the username.
- `POST /evidence` unsigned → **401 in 0.06s** (was a 504 after five minutes).
- `POST /evidence` correctly signed → `{"accepted": 1, "stored": 1}`.
- Replayed identical batch → `{"stored": 0, "duplicates": 1}`. **That is also
  the persistence proof**: the dedupe check reads history back out of
  Firestore, so it could only recognise the duplicate if the first row was
  durably stored.

**One trap closed:** `openssl rand -hex` emits a trailing newline and
`secret_from_env` encodes the value verbatim, so the stored secret ended in
`\n` while a collector exporting it from a shell file would not — a signature
mismatch with no visible cause. Both secrets rewritten without it (version 2)
and the revision bounced. **Worth considering in code**: stripping the secret in
`secret_from_env` would make the two agree regardless of how each side stores
it.

Left behind deliberately: a `smoke:deploy-check` surface in Firestore from the
end-to-end proof. Harmless, and it is the evidence the rail works.

### Session: 2026-08-11 — DM2 merged (PR #7) after closing ten security findings

**The sprint shipped seven of nine tasks, and the security gate was right to
block the first attempt.** All thirteen audit findings were verified against
the branch before any were acted on; **none was a false positive**, which is
worth recording because the usual triage result is mostly noise. Ten are
fixed, four deferred to DM3 with stated reasons.

The two that mattered most were the two the auditor named regardless of its
own severity ranking:

- **`read_at` had no upper bound.** `_judge_surface` asked only whether age
  *exceeded* the silence window, so a future-dated row had negative age, never
  went stale, and — because the store orders by `read_at` — also stayed newest
  forever. A single collector with a forward-skewed clock permanently disarmed
  the staleness detection this entire sprint exists to build. No attacker
  required. Now refused at the wire and judged `UNOBSERVABLE` rather than fresh
  for rows already stored.
- **The public board republished the estate.** `GET /` is
  `--allow-unauthenticated` with a published URL, and `_evidence_row` emitted
  `detail` and `source` verbatim: collector absolute paths, collector id,
  arrival times. `deadman.redact` now gates on the *shape* of a value rather
  than a key allowlist, because an allowlist fails open the first time a probe
  adds a key nobody classified. Withheld keys are named, not silently dropped.

**One design decision worth carrying forward:** the client-identity guard
(finding #6) lives at the wire, not at annotation. `on_arrival` deliberately
*preserves* `wire_row_id`/`reported_method` when present, so re-annotating
cannot launder a relayed row into a fresh one — and that preservation is only
safe because `decode_row` now strips every service-owned key from untrusted
input. Fixing it at the annotation site instead would have broken the
laundering guard, which is what the existing test caught.

`verify/surface_verdict.py` was split out of `collector_liveness.py` because
the new guard pushed it past the 200-line arch cap. Split on the seam the file
had actually grown rather than trimming prose to duck the gate.

Gates: **568 passed** (up from 528), ruff clean both ways, `arch check
--strict` clean over every tracked file, CI green, merged to `main` at
`4b2666e`.

**⚠ THE DEPLOY DID NOT FOLLOW THE MERGE.** `gcloud` is not present on this Mac
*or* on the rig (both checked), so the live service at
https://deadman-mrapac5nda-uc.a.run.app is **still running DM1 code**. None of
DM2 is live: no ingest endpoint, no durable store, no board redaction. The
deployed image tag is now stale against `main`, which is exactly the condition
the handoff warns about. **This is the first thing the next session should
fix**, and it needs an operator with gcloud installed and authenticated.

### Session: 2026-08-11 — DM2.6 blocked: the scheduled self-check is real, the live infra is not yet touched

New package `src/deadman/scheduled/` (`auth.py`, `endpoint.py`), mirroring
`deadman.ingest`'s shape but simpler — there is no body to authenticate, only
a trigger, so it's a bearer token compared with `hmac.compare_digest` rather
than an HMAC-over-bytes scheme. `DEADMAN_SCHEDULER_SECRET` is mandatory at
import, same doctrine as `DEADMAN_INGEST_SECRET`: a missing secret is a
refusal, not a default, because a public endpoint that triggers work is a
free denial-of-service.

`src/deadman/self_check.py` gained `SelfEvidenceSink` (a `Protocol` both the
old filesystem log and the new store-backed one satisfy — `self_check()` and
`run_self_check()` needed no behavior change, just a broadened type hint) and
`StoreSelfEvidenceLog`, which writes through the DM2.1
`EvidenceStore` on surface `self:sweep` instead of a per-instance file. This
is what retires DM1.11's stated cold-start limitation: a fresh Cloud Run
instance shares no filesystem with the one that swept before it, but it does
share the store.

`ScheduledSelfCheckEndpoint.handle` (in the new package) checks the secret,
reads the *prior* row's liveness before writing a new one — checking after
writing would always read LIVE, since the row just written is by
construction fresh, and a self-check that cannot fail proves nothing — then
sweeps `default_probes()` and records through the store. Wired into
`deadman.service.build_app` via `default_scheduled`, alongside the existing
`ingest` and `liveness_fn` optional endpoints on `make_app`.

**Reducing import count paid for the wiring.** Adding two new `from`-imports
to `service.py` tripped `arch check --strict`'s "more than 20 imports"
threshold (`21 > 20`). Fixed by importing `deadman.scheduled` as a namespace
(`from deadman import scheduled as scheduled_pkg`) rather than importing
each name separately — one import statement instead of two, and it also
sidesteps a real shadowing bug the alias route would have hit: `make_app`'s
own parameter is named `scheduled`, so `from deadman.scheduled import
ScheduledSelfCheckEndpoint` inside that function's closure would have made
`scheduled.handle(...)` resolve to the *parameter* (the endpoint instance),
not the module, the moment both were in scope with the same name.

34 new tests across four files (`test_scheduled_auth.py`,
`test_self_check_store.py`, `test_service_schedule.py`,
`test_scheduled_startup.py`), all passing on first run against the
implementation — the design was worked out from reading the existing
`ingest`/`self_check`/`store` modules closely enough that the auth,
routing, and cold-start-survival tests needed no iteration.
`test_service_schedule.py::TestSelfEvidenceSurvivesACleanReadFromAnotherInstance`
is the AC5 proof: two independently-built `make_app` instances, each with
its own `ScheduledSelfCheckEndpoint` and `StoreSelfEvidenceLog`, sharing
nothing but one `InMemoryEvidenceStore` — the second instance never received
the first's request, and still reads `liveness_before: "live"` off the
row the first one wrote.

**Blocked on two ACs, not done: enabling Cloud Scheduler and verifying a
fired job.** See Blocker 5. This sandboxed worktree has no `gcloud` CLI
(`command not found`) and no ADC (`~/.config/gcloud` absent), discovered
before writing `infra/scheduler.md` rather than assumed. Every command that
touches the live project — API enable, secret provisioning, job creation,
the trigger-and-read-back verification via `FirestoreEvidenceStore` — is
written out exactly and reproducibly in `infra/scheduler.md`, following the
same "runbook nobody has executed is a hypothesis" discipline DM1.8 and
DM2.7 already paid for, but not run. `bpsai-pair task update DM2.6 --status
done` correctly refused on the two unchecked items; set to `blocked` rather
than forced through. Every other AC is checked off with evidence in
`.paircoder/tasks/DM2.6.task.md`. Gates: `pytest -n auto --dist=worksteal`
528/528, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch
check --strict` clean.

### Session: 2026-08-11 — DM2.5 done: real surfaces, one already broken

Wired the collector to actual infrastructure rather than synthetic tests. 9
new tests (494 total, up from 485), all four gates clean.

**The morning brief fault is captured for real, not described.**
`MorningBriefProbe` was run this session against the real
`~/ops/data/brief-send-log.jsonl`: `FAULT`, "no brief sent in 176.7h (window
30h, ~7 missed)", last real send `2026-08-04T11:56:45`. That evidence is
committed verbatim as `tests/fixtures/real-morning-brief-fault.json`
(new directory, own README distinguishing it from `tests/recorded/`'s
authored-or-captured *model* responses — this is a captured *probe* reading,
no model involved), pinned by `tests/test_real_evidence_fixtures.py` so a
future recapture that happened to land `HEALTHY` (the ops bug got fixed)
would fail loudly rather than quietly stop being evidence of anything.
DM2.9's case study reads from this rather than from memory.

**Two machines, one probe, and a surface id that cannot collide.**
`DiskProbe` gained a `host` field (`src/deadman/probes/disk.py`), blank by
default so `service.py`'s own Cloud Run probes (`host:disk/`, watching the
ephemeral container filesystem, unrelated to the real Mac or rig) are
untouched. Set to `"mac"` or `"rig"` it produces `host:mac/disk` /
`host:rig/disk` — a naming scheme every correlation/diagnose/ingest test
fixture already assumed (`host:mac/disk` appears dozens of times across
`tests/recorded/*.json` and elsewhere) but that no real probe had ever
actually produced until now. `infra/collector/collector-rig.example.json` is
new and is the entire proof of the "config edit plus an existing probe" AC:
same `disk` probe type as the Mac's config, different `host`/`collector_id`,
zero new probe code. `infra/collector/collectors.example.json` now declares
both collectors.

**"Missing path" got an explicit `detail["path"]`, not just an embedded
string.** Both `DiskProbe`'s `unobservable()` call (missing volume) and
`MorningBriefProbe._missing_log_result`'s (missing log directory) now pass
`path=` explicitly, so a caller can read the misconfigured path without
parsing an exception message out of `source`. Required updating
`scripts/generate_samples.py`'s redaction step, since the new `detail.path`
leaked the generator's temp directory into `sample-outputs/board.json` —
`test_the_generator_is_deterministic` caught it immediately.

**"Never hardcoded" is now asserted, not just structurally true.**
`tests/test_collector_config.py::test_a_probes_real_path_comes_from_config_never_a_hardcoded_literal`
builds two probes from two never-before-seen paths and asserts each probe's
path matches its own config exactly and differs from the other's — round-trip
proof rather than an inference from `build_probes`'s existing coercion tests.

**`docs/surfaces.md` is new**: the concrete counterpart to
`docs/ARCHITECTURE.md`'s abstract "Surfaces (v1)" table — real path, real
cadence, and what blindness means, per surface actually deployed
(`cron:morning-brief`, `host:mac/disk`, `host:rig/disk`), plus a three-step
"adding another surface" recipe.

Files: `src/deadman/probes/{disk,morning_brief}.py`, `docs/surfaces.md`,
`docs/ARCHITECTURE.md`, `infra/README.md`, `infra/collector/
{collector.example.json,collector-rig.example.json,collectors.example.json}`,
`scripts/generate_samples.py`, `sample-outputs/board.json`,
`tests/fixtures/{README.md,real-morning-brief-fault.json}`,
`tests/test_real_evidence_fixtures.py`, and updates to four existing
collector test files.

Gates: `pytest -n auto --dist=worksteal` 494/494 (up from 485); `ruff check .`
and `ruff format --check .` clean; `bpsai-pair arch check --strict` clean.

### Session: 2026-08-11 — DM2.4 done: absence no longer reads as health

`src/deadman/verify/` is new: `expectations.py` (what each collector promised)
and `collector_liveness.py` (whether it kept the promise). 73 new tests (485
total, up from 412), all four gates clean.

**Cadence is declared, and the module split is what enforces that.**
`expectations.py` holds nothing but the declaration and never sees a store, so
a deadline has literally nowhere to come from except configuration. The
failure being refused: a collector that dies slowly — every 15 minutes, then
hourly, then daily — teaches an inferring monitor to expect exactly the
silence it is producing, and the board stays green the whole way down.
`grace_intervals` defaults to 1.0, so silence is a fault at the cadence plus
one whole missed run (30 minutes for the Mac's declared 900s).

**Two clocks, because there are two questions.** Collector liveness is about
*delivery* and is timed by `received_at`; surface freshness is about *reading*
and is timed by `read_at`. Store-and-forward makes that real rather than
pedantic: a collector that lost the network for a day and then drained its
spool is alive — it just shipped — while every reading in that spool is a day
old. The board now says both, which it can only do because DM2.2 recorded when
we heard separately from when it was seen.

**A stale surface reads `UNOBSERVABLE` whatever it last said, including
FAULT.** Not a lost alarm: blindness is counted on its own line, the collector
is faulting beside it, and the previous observation survives in
`detail['last_observation']`. What is refused is asserting a current verdict
from a reading too old to be one, in either direction.

**The board gained four fields** (`collectors_declared`, `fresh_count`,
`stale_count`, `unreported_count`, `undeclared_surfaces`) — additive, so the
DM1 contract DM2.8 has to stay compatible with is intact. `fresh`/`stale`/
`unreported` partition the declared surfaces, so "no faults" and "nothing
reported" can no longer be the same number. `sample-outputs/board.json` was
regenerated by script accordingly.

**`scripts/mutation_check.py` is committed, and it is the AC.** Eleven guards,
each inverted in the source one at a time, each required to break one named
test; a mutation that survives exits non-zero as an unprotected guard. All 11
are currently caught. The `DEADMAN_COLLECTORS` env var is documented in
`infra/README.md` with `infra/collector/collectors.example.json` beside it —
and a test cross-checks that example against `collector.example.json`, so a
surface declared on one side but not swept on the other fails the suite.

**Known limit, stated rather than hidden:** arrivals are searched through the
newest 50 rows per surface by `read_at`, so a spool older than that many newer
readings can have its delivery missed. That reads as silence — an alarm, never
a false green.

### Session: 2026-08-11 — DM2.3 done: the collector sweeps where the surfaces actually are

`src/deadman/collector/` now holds the process that runs on Kevin's machines:
`config.py`, `transport.py`, `spool.py`, `run.py`. 50 new tests (412 total, up
from 362), all four gates clean.

**Which probes run is a fact about a JSON file, never the collector's
source.** `config.py`'s `PROBE_TYPES` maps a type name to the real dataclass
(`DiskProbe`, `MorningBriefProbe`); `build_probes` constructs them, coercing
string arguments to `Path` by reading the *target dataclass's own field
annotations* rather than hand-coding which argument name means "this is a
path" per probe. That is the one mechanism a probe registered later —
DM2.5's job — needs nothing new here to use. `infra/collector/
collector.example.json` is not just documentation: `test_collector_example_
config.py` loads and builds real probes from it, so the README's own example
can't drift from what the parser actually accepts.

**Probe isolation cost nothing to add because it was not reimplemented.**
The collector calls `deadman.probes.base.sweep()` directly — the same
never-raise contract DM1 built — so "a raising probe doesn't blind the rest
of the sweep" is inherited, not a second copy of that rule to keep in sync.

**Store-and-forward has exactly two outcomes for a row: shipped, or still
spooled.** `spool.py`'s `Spool` keeps nothing in process memory — every
method reads or writes its directory directly, one file per failed batch,
named so filename order is delivery order. That is what makes the restart
AC free rather than engineered: a second `Spool` (or `Collector`) built with
no reference to the one that failed sees exactly what was left on disk,
because the directory *is* the state. A non-200 reply is spooled exactly
like a connection failure — `transport.py`'s `TransportError` names only
"never reached a server that could answer"; a service that answered and
refused is a different fact, but both mean the batch is not yet delivered.

**A resend is a fresh signature, not a replayed one — the subtle part.**
DM2.2's freshness window is five minutes; a spool can sit far longer than
that while a network is down. Reusing the original `signed_at` would make
an honest retry look like a stale replay and fail on arrival, exactly
backwards for a store-and-forward mechanism. So every send — first attempt
or the Nth retry — builds a fresh `Batch` at the current clock reading and
signs *that*, while each evidence row keeps its own original `read_at`
untouched. `test_the_resent_batch_is_freshly_signed_not_replayed_stale`
pins it with a clock that jumps 6 hours between the failed and the
recovering send.

**Dry run is real, not simulated.** `--dry-run` never calls
`self.transport` at all — not "calls a mock", calls it *zero times* — so
`test_dry_run_makes_zero_network_calls_under_the_real_transport` runs it
with the actual `UrllibTransport` inside the suite's hermetic socket block
from `conftest.py`. A pass means it structurally cannot have dialed out, not
that a fake happened not to be called.

**A malformed config fails loudly, naming the offending key**, at every
layer: a missing top-level key, a bad `probes[i].type`, args that don't
match the target constructor, `DEADMAN_INGEST_SECRET` unset — each raises
naming the specific thing that's wrong, and the CLI (`main()`) catches these
at startup and exits non-zero with the message on stderr rather than a
traceback or a silent empty sweep.

**`infra/launchd/com.deadman.collector.plist` + README, both executed, not
just written.** The plist is a LaunchAgent (not a Daemon — no root needed to
sweep files Kevin's own account can read), `StartInterval` not
`StartCalendarInterval` (a sleeping laptop catches up on wake instead of
skipping a day), and carries no secret — the shared ingest secret is sourced
from `~/.deadman/collector-env.sh` at run time, unchecked-in, matching the
rule DM2.2 already enforces on the service side
(`TestNothingSecretIsCommitted`). Verified by hand this session: `plutil
-lint` on the template and on a `sed`-materialized copy with real paths
substituted (both `OK`), and the README's own `deadman-collector --dry-run`
command run for real against the example config. `launchctl load` itself
was not run — installing a live recurring background job on this machine is
outside what this session should do unattended; that step is Kevin's to run
by hand from a documented, executed command.

Files: `src/deadman/collector/{__init__,config,transport,spool,run}.py`,
`infra/launchd/com.deadman.collector.plist`, `infra/collector/
collector.example.json`, `infra/README.md` ("The collector" section),
`docs/ARCHITECTURE.md` ("The collector: where evidence actually gets
produced"), `pyproject.toml` (`deadman-collector` console script), five new
test files.

Gates: `pytest -n auto --dist=worksteal` 412/412 (up from 362); `ruff check
.` and `ruff format --check .` clean; `bpsai-pair arch check --strict`
clean.

### Session: 2026-08-11 — DM2.7 blocked: the alarm is real, the rail it sends over is not

`src/deadman/remediate/transports.py` now holds everything DM1.11's
`AlertChannel` was missing: `EmailTransport` (stdlib `smtplib` +
`email.message`, no new dependency — STARTTLS, login, `send_message`, the
same shape as `ops/lib/email_send.py`), `email_transport_from_env` (six
`DEADMAN_ALERT_*` variables, refuses via `EmailTransportNotConfigured` if any
are missing, no hardcoded credential defaults),
`real_monitored_surfaces()` (reads `deadman.service.default_probes()`
directly rather than a retyped literal — DM1.11's own test used a hand-typed
tuple, and this is what replaces that with the real thing),
`ThrottledAlertChannel` (documented 1h window, suppresses only a *repeat* of
the same state, never a state change), and `record_transport_failures`
(wraps `send` so a failure is appended to the DM2.1 store as `FAULT` on
`alert:email` before re-raising — the raise stays, per `AlertChannel.alert`'s
"a swallowed alert is silence" contract). 20 new tests in
`tests/test_transports.py`, all passing first run; the two behavioral guards
the ACs call out (state-change-always-delivered, failure-not-swallowed) were
mutation-checked by hand (`PYTHONDONTWRITEBYTECODE=1`), each caught by a
named test.

**Found and fixed in passing, unrelated to this task's file scope:**
`tests/test_ingest_startup.py`'s own secret-scanning test
(`TestNothingSecretIsCommitted`, from DM2.2) tripped on its own docstring —
the RST literal markup `` ``DEADMAN_INGEST_SECRET=`` `` in its prose was
captured by the `git grep` regex as a "committed value" of `` `` `` because
backtick wasn't excluded from the character class. Pre-existing on `HEAD`
before this session touched anything (confirmed via `git show`, only one
commit — DM2.2's own — has ever touched that file); fixed by excluding
backtick from the captured value and treating a genuinely empty capture
(nothing followed `=` before a delimiter) as inherently non-secret rather
than a failure. `pytest -n auto --dist=worksteal` was reporting 341/342
before this fix.

**Blocked on one AC, not done: "one real message is confirmed received."**
Checked whether a real send was possible before writing anything — this
project's own rule, paid for once already by DM1.8's live-deploy blocker, is
that a runbook nobody has executed is a hypothesis. `ops/.env`'s active SMTP
block is labelled in its own comment `# DUMMY SMTP — for T87.2 testing only.
Real sends will fail at connect`; the real values it would use in production
sit commented out, never activated.
`ops/monitoring/alertmanager/alertmanager.yml` independently confirms email
delivery is still a `# In production, add:` TODO there, and ops carries its
own standing backlog item for this
(`backlog-sprint-T152-outbound-email-rail.md`). **The "existing ops email
rail" this task was scoped against does not yet exist as a working,
deliverable rail** — that is a fact about a sibling repo, not a defect in
this one. No credential value was read into this session beyond confirming
that comment and the two commented-out variable *names*; nothing was printed
or logged.

Every other AC is met and checked off in `.paircoder/tasks/DM2.7.task.md`,
including the wiring AC (`real_monitored_surfaces()` sourced from the actual
probe list) and `docs/alerting.md` (written with the blocked finding
recorded plainly rather than a fabricated "confirmed received"). Gates:
`pytest -n auto --dist=worksteal` 362/362, `ruff check .` and `ruff format
--check .` clean, `bpsai-pair arch check --strict` clean.
`bpsai-pair task update DM2.7 --status done` correctly refused on the one
unchecked item; set to `blocked` rather than forced through.

### Session: 2026-08-11 — DM2.2 done: authenticated ingest, and the arrival rule

`src/deadman/ingest/` now holds `POST /evidence`, wired into `service.py`. 77
new tests, 342 passing, all four gates clean.

**The rule that made this task worth doing: arrival caps every method at
`REPORTED`.** The service did not read the disk; a collector says it did.
Recording that as `LOCAL_ARTIFACT` would have Cloud Run assert it inspected a
disk it has no access to. The cap is a table (`ON_ARRIVAL`), total over
`Method` by test, so a method added later must be graded deliberately rather
than by a silent `dict.get` default.

**What that costs is the point, and it is written down rather than routed
around.** Every action floor in `remediate/registry.py` sits above the 0.4
confidence ceiling `diagnose/grounding.py` puts on a `REPORTED` citation, so a
diagnosis resting only on collected evidence escalates to a human instead of
moving infrastructure. Since every real DM2 surface is remote, that disables
automated remediation on collected evidence — which is the correct reading of
what the service actually knows. The collector's claim survives in
`detail.reported_method`: downgraded, not erased.

**Idempotency forced a distinction the store could not have made.** DM2.1's
`row_id` hashes the encoded row, and an arriving row must carry
`detail.received_at` — our clock, distinct from the collector's `read_at`. So a
re-sent batch hashes *differently* as a stored row and the store's own dedupe
would not have caught it. Identity therefore belongs to the observation, not to
our bookkeeping about it: `detail.wire_row_id` is computed before annotation
and is what ingest compares. A test pins that keying on the stored row instead
fails. One honest limit, named in the module: the replay lookback is 200 rows
per surface, and a replay older than that stores a recognisable second copy
(same `wire_row_id`, same `read_at`, later `received_at`) rather than a silent
doubling of the trend.

**Auth verifies the raw bytes before parsing anything**, so nothing
unauthenticated is ever interpreted, and `signed_at` lives *inside* the signed
payload — a timestamp in a header sits outside the MAC and the freshness check
it feeds would be decorative. The window is bounded in both directions;
one-sided lets a captured body be replayed forever by dating it forward. Note
what freshness is not: it is not the replay defence for an honest collector
retrying a spool it could not deliver. Refusing those would drop evidence
exactly when the network is already unreliable.

**`service.py` refuses to import without `DEADMAN_INGEST_SECRET`**, proven in a
real subprocess with the variable stripped (DM1.11's discipline: "refuses to
start" is a claim about a process). `tests/conftest.py` therefore sets a
throwaway secret for the suite.

**Ten mutations, ten named tests**, `PYTHONDONTWRITEBYTECODE=1` throughout —
identity arrival mapping, endpoint storing without downgrading, signature check
removed, freshness removed, dedupe keyed on the stored row, dedupe keyed on
surface alone, body cap removed, missing secret defaulting to empty, unknown
wire method coerced to the weakest tier, one-sided freshness window. Each broke
a specific test. The endpoint suite passed 21/21 on its first run, which is
precisely when this repo's own doctrine says to be suspicious.

**Two things found by writing the docs rather than the code.** The `curl`
runbook in `infra/README.md` was executed, not asserted (DM1.8's lesson): the
exact body is verified to make `openssl dgst -hmac` and `auth.sign` agree, and
to store with `method='reported'`. And the first draft of the
"no secret is committed" test failed on its own documentation — a `git grep`
for the variable name cannot distinguish a pasted token from a runbook telling
an operator how to set one, so the rule now tests the *value*.

**Deploy path closed, per DM2.1's handoff.** `Dockerfile` installs
`.[firestore]` and `cloudbuild.yaml` sets `DEADMAN_STORE_BACKEND=firestore`
with `--update-env-vars`, never `--set-env-vars`, which would replace the whole
environment and wipe the ingest secret on every deploy. The memory backend
stays the local default but now announces itself on stderr: a deploy that
missed the variable would otherwise answer a collector `stored: 1` for evidence
that dies at the next scale-to-zero, which is a false green nobody would find
by looking at the board. **The deploy itself is unrun here** — no gcloud in
this session, and it is DM2.6's privileged step. Firestore prerequisites
(database creation, `roles/datastore.user`) are documented in
`infra/README.md`.

### Session: 2026-08-11 — DM2.1 done: the evidence store seam

`src/deadman/store/` now holds the `EvidenceStore` Protocol and two backends
behind it. 29 new tests, 265 passing, all four gates clean.

**The Protocol is `append` / `latest` / `latest_per_surface` / `history`.**
`history` is there for DM2.8 rather than for DM2.1, deliberately: this seam
feeds four downstream tasks, and discovering in DM2.8 that held-duration needs
a read the Protocol does not have would mean reopening the contract after
three consumers depend on it. It is contract-tested now, so it is not
speculative surface.

**Absence stayed a state.** `latest()` on a surface with nothing stored
returns `unobservable(...)` — never `None`, never a synthesised healthy row.
Returning `None` would have pushed the judgement onto every caller, and one
caller writing `if not evidence` would reinstate the false green the whole
project argues against.

**Replay safety fell out of content-addressed row identity.** `row_id()`
hashes the encoded row, so an identical observation appended twice stores
once, and a document backend writes with `set` instead of racing a
read-modify-write. DM2.2's idempotent-batch AC gets this for free. Rows
differing only in `read_at` are kept apart on purpose — collapsing those
would erase the history DM2.8 computes held-duration from.

**The Firestore backend is contract-tested, not merely written.** The suite is
hermetic and the SDK is never installed, which would normally leave the
deployed backend as the one nobody tests. Instead the backend takes an
injected client and `tests/firestore_double.py` reproduces the narrow API
slice it calls — including two behaviours that would otherwise surface only in
production: Firestore document ids may not contain `/` (the surface
`host:mac/disk` does, and the double caught the missing percent-encoding), and
a collection query skips documents that exist only as subcollection parents.

**Six mutations, six named tests.** Unencoded surface key, ascending Firestore
ordering, memory ordered by arrival rather than `read_at`, absence synthesised
as healthy, row identity by surface alone, dedup removed — each fails a
specific test. A seventh check confirmed the AST seam guard fires on an
injected module-scope `from google.cloud import firestore`, which is the half
of the zero-dependency promise that must hold on a machine where the SDK *is*
installed.

**One thing left for whoever wires Firestore into the service:** the Dockerfile
still installs `.` with no extras. Correct today — nothing constructs a
`FirestoreEvidenceStore` — but DM2.2 or DM2.6 must change it to `.[firestore]`
or the service fails closed at startup on the deploy rather than in CI.

### Session: 2026-08-11 — DM2 planned (`/pc-plan DM2-make-it-real.md`)

Materialized 9 task files under `.paircoder/tasks/` from
`plans/backlogs/DM2-make-it-real.md`. Plan `plan-2026-08-dm2-make-it-real`
already existed with all 9 ids registered in its phase; the task files were
what was missing, and `bpsai-pair status` was reporting all 9 as not found.

Each task file carries objective, files-to-update, an implementation plan
anchored to the actual code it extends, the backlog's ACs, and verification
commands. Added a **wiring AC** to seven of the nine — the backlog's ACs are
strong on behavior but several would pass over a module that was written,
unit-tested, and never called. Each names a call site, a configuration source
with its default, and a failure mode.

**Model assignments follow the backlog, not the calibration doctrine.**
`calibration recommend-model` returns `claude-sonnet-5` for every complexity
in this sprint (25–35) and `claude-opus-4-8` with `--cross-module`, both
flagged `insufficient_samples`. The backlog assigns `claude-opus-5` to the
four seam-defining tasks (DM2.1, DM2.2, DM2.4, DM2.9), which matches DM1's
own convention — five of twelve DM1 task files carry `claude-opus-5`. The
config's `models.providers.anthropic.models` list is stale relative to what
the repo actually uses.

PM provider is `none`, so this is local-only planning: no sync step.
`bpsai-pair validate` passes; budget check per task ~20k tokens (2%), well
under the 75% threshold.

### Session: 2026-08-11 — DM1.12 integration gate, sprint complete

**Rehearsing the demo live is what made this task worth doing.** It found a
defect nothing else could: `verify_remediation` raised `ValueError` when a
diagnosis cited nothing, because its guard could not tell apart a caller
passing an unrelated probe (a programmer error, worth being loud about) from
every citation being rejected (ordinary reality on a non-deterministic model).
Four identical live runs gave three grounded diagnoses and one that read
correctly while citing nothing. The fourth crashed. It now returns
`NOT_ATTEMPTED`, because a monitor that dies whenever its model has an off
moment has become the outage it was watching for.

**That variance is documented, not hidden.** `docs/DEMO.md` carries the real
rehearsal table (4.6s / 7.8s / 7.0s / 10.5s, three healed, one correctly
refused to act) and instructs whoever records the take to narrate the refusal
rather than re-roll it. An agent declining to act on its own model's uncited
assertion is the whole argument, and no scripted success shows it as well.

**First real Gemini capture committed.** Recordings carry a `captured` flag and
most are `false`, which is honest but weak: an authored fixture only proves the
parser handles a shape we invented. `captured-disk-cascade.json` is verbatim
from live `gemini-3.5-flash`, replayed by `tests/test_diagnose_captured.py`,
and when it disagrees with an authored fixture the authored one is wrong. In
it, the model identified disk exhaustion as upstream of the Metricool failure
at 0.9 confidence with quoted citations, and the trust ceiling capped that to
0.4, which then fell below the action's floor and produced an escalation
rather than an act. The system disagreeing with its own model, in a committed
sample.

**Also shipped:** `sample-outputs/` generated by script and enforced byte for
byte by a test; `docs/architecture.png` with the inferential band fenced off
explicitly; a README that opens on the failure class rather than installation
and closes with five real limits; and a clean-clone check run verbatim.

Gates: 236 passed, ruff clean both ways, arch check clean.

### Session: 2026-08-10 — DM1.11 self-liveness and out-of-band alerting

Eleven of twelve done. Built TDD across nine red-green cycles.

`src/deadman/self_check.py` proves liveness from a row appended *after* a
sweep completes, never from a heartbeat or a process start. The timestamp is
read from inside the row rather than from file mtime, same lesson as the
morning brief probe. That test was mutation-checked: swapping `latest()` for
the naive `os.path.getmtime` version fails it, so it has teeth rather than
passing by construction.

Three liveness states, not two. `NO_EVIDENCE` is deliberately distinct from
`STALE`, because "it stopped" and "it never started, or we are pointed at the
wrong path" call for different responses, and both exit non-zero. Treating no
data as nothing to report is exactly how a monitor goes quiet unnoticed.

`src/deadman/remediate/alert.py` refuses at construction to sit on a rail
deadman watches, and refuses the whole rail rather than the exact id: with
`sms:relay` monitored, `sms:backup-number` is the same physical path with a
different destination and dies at the same moment. Checked at startup because
when the alarm is needed, the channel is as likely to be down as the thing it
would report. That is the nine-day outage as a constraint: nobody ignored an
alert, there was no alert.

Wired into the service so it is real rather than theoretical. A served board
records self evidence; a rejected 405 does not, since a stream of bad requests
must not forge liveness for a service whose probes never ran. Added a
`[project.scripts]` console entry point, so "exits non-zero" was verified as a
property of a command a scheduler runs: `deadman-self-check` exits 1 on stale,
1 on no-evidence, 0 on live, checked as real processes.

**Known limitation, stated in `default_self_log` rather than left to be
found:** Cloud Run's filesystem is per-instance, so this proves an instance's
liveness, not the service's across cold starts. Durable self-evidence is v2.

Gates: 222 passed (up from 212), `ruff check` and `ruff format --check` clean,
`arch check --strict` clean on both new modules.

### Session: 2026-08-10 — DM1.8 deployed live, and the Gemini path proven

Two blockers that had stood since the sprint began are both gone. GCP access
now exists on the rig, which is what unlocked them.

**DM1.8 is done, and deploying it broke twice first.** Live at
https://deadman-mrapac5nda-uc.a.run.app, public, returning the board. Three
defects stood between the committed config and a reachable service:

- `cloudbuild.yaml` assembled its image reference through nested
  substitutions. Cloud Build does not expand a substitution inside another
  substitution's default value, so `gcr.io/${PROJECT_ID}/deadman:latest`
  reached the builder as that literal string. `SHORT_SHA` could not stand in
  either: it is a built-in that populates only for trigger-based builds.
- `--allow-unauthenticated` was not sufficient by itself. Cloud Build's
  service account deployed the revision without permission to set the IAM
  policy, so the build reported SUCCESS while every request got 403 from the
  Google frontend, before reaching the container. Nothing in the output
  connects those two facts. A one-time `run.invoker` binding fixes it.
- The README documented a deploy command nobody had ever run, and the command
  was wrong. Testing the fresh-clone AC by executing the README verbatim is
  what caught it.

**The live Gemini call happened, which retires the eligibility risk.**
`gemini-3.5-flash` through the ADK returned a structured `Diagnosis` with
citations. Two findings, both in `docs/gemini-verification.md`:

- `gemini-3.5-flash` is served **only from the `global` Vertex endpoint** and
  404s in `us-central1`. Matching the location to the Cloud Run region is the
  natural instinct and it silently costs you the required model.
- A freshly created service account returns 403 on predict for roughly a
  minute while the IAM binding propagates, which looks exactly like a missing
  role. Verify the binding before changing anything.

The most useful result was the content of the diagnosis, not the fact of it.
Handed a real fault with no cause anywhere in the evidence, the model declined
to name one: *"the available evidence is insufficient to determine the
underlying cause."* The grounding rules are enforced offline against fixtures
we wrote, which only proves our fixtures obey our rules. This is the first
evidence that a real model behaves the same way.

**Also closed a gate gap.** CI ran `ruff check`, which does not police
formatting, so 16 source and test files had drifted while every build stayed
green. Added `ruff format --check` and `pytest -n auto`. Worth recording that
adding the gate immediately broke CI: reformatting the bpsai-pair scaffolding
in `scripts/cc_hook.py` pushed a function from under the 50-line cap to 80 and
failed `arch check --strict`. **Arch check has to run after the formatter.**
That file is now excluded from formatting, since bpsai-pair regenerates it.

### Session: 2026-08-11 — DM1.7 verification loop (`/start-task DM1.7`)

- **The gap this closes:** `ActionResult.performed` (DM1.6) is a fact about
  the process — the code ran and did not raise. Nothing before this task
  could tell a caller whether the surface actually recovered.
  `deadman.remediate.verify.verify_remediation` is the only thing allowed to
  say "fixed", and it says so on exactly one basis: a fresh
  `Observation.HEALTHY` from re-running the *same probe* that reported the
  fault, through the same never-raise `run_probe` contract detection uses.
- **"Cannot be re-observed" is coded as its own outcome, not folded into
  success.** If the probe goes blind on re-run, `run_probe` contains the
  raise as `UNOBSERVABLE`, never `FAULT` — and the loop treats that exactly
  like any other non-`HEALTHY` result: unverified. Blindness about whether a
  fix worked gets the same honesty the rest of the project applies to
  blindness about the original fault.
- **The probe has to be the one the diagnosis is actually about.**
  `verify_remediation` checks the probe's surface against the surfaces
  derived from `diagnosis.evidence_ids` and raises `ValueError` on a mismatch
  — re-observing an unrelated surface would prove nothing about the fault
  that was acted on. `test_verifying_against_an_unrelated_surface_is_refused`
  pins it.
- **Repeated failure stops rather than looping.** Each attempt re-plans and
  re-executes against the same diagnosis/evidence (the world can change under
  the action even though the inputs do not), bounded by `max_attempts`
  (default 3). Success stops the loop immediately; exhausting the cap without
  a `HEALTHY` reobservation returns `VerificationStatus.EXHAUSTED`, never an
  unbounded retry. A third terminal status, `NOT_ATTEMPTED`, covers the case
  where the executor escalates on the first plan — nothing ran, so there is
  nothing to re-observe, and the probe is never called.
- **All four guards mutation-checked** (same discipline as DM1.5/DM1.6/DM1.10,
  `PYTHONDONTWRITEBYTECODE=1` throughout): the `HEALTHY`-only success check,
  the `NOT_ATTEMPTED` early-return on escalation, the surface-match
  validation, and the `max_attempts` cap each broke a specific named test
  when inverted.
- Files: `src/deadman/remediate/verify.py`, `tests/test_remediate_verify.py`
  (8 tests), `docs/ARCHITECTURE.md` (new "The verification loop closes the
  honesty gap" section).
- Gates: `pytest tests/` 200/200 (up from 192); `ruff check .` clean;
  `bpsai-pair arch check --strict` clean.
- **Not wired into `service.py` yet, same reason as DM1.6/DM1.10.** This is a
  library call — `verify_remediation(executor, probe, diagnosis, evidence)` —
  with no call site here because nothing upstream of it (a live executor with
  real capabilities, a live diagnosis engine) is wired into the endpoint
  either. DM1.12 is still the integration point that has all three.

### Session: 2026-08-11 — DM1.10 cross-surface correlation (`/start-task DM1.10`)

- **The question this turned on:** co-occurrence is nearly worthless as
  evidence, so what actually establishes that two faults are related? Every
  probe in a sweep runs within milliseconds of every other, so two faults share
  a `read_at` whether or not they share a cause — and `read_at` is when *we
  looked*, not when the fault began. Treating that agreement as evidence would
  be numerology. So the window **proposes and the cited evidence disposes**:
  `correlate/window.py` decides which faults are worth one question and
  contributes *nothing* to confidence; membership in the incident is read off
  the citations, never off the window.
- **The gate that makes this more than a time-bucket:** a relationship requires
  quoted evidence from two or more *faulting* surfaces. `grounded-disk-only` is
  the test that proves it — a perfectly good grounded diagnosis over the same
  three co-occurring rows, which happens to be a diagnosis *about the disk*.
  Three broken things in one window, no correlation.
- **Blindness is never a leg, enforced twice.** A lone fault beside an
  `UNOBSERVABLE` row is not a candidate, and — separately, because the model
  chooses what it cites — a grounded hypothesis that ties a fault to a blind
  surface is not a correlation. New recording `grounded-blind-relay-tie` is
  exactly that: fully grounded, quotes the disk trend *and* the relay's own
  "cannot observe", two surfaces, two citations, one tidy story, refused. A
  relay we could not reach cannot corroborate anything.
- **Confidence is carried, not recomputed.** The incident's number is the
  diagnosis's own capped number. The flagship case lands at 0.4 from a claimed
  0.7 — because the tie to the scheduler runs through a `REPORTED` row — and
  both numbers are rendered, so the cap reads as a cap rather than a quiet
  subtraction. What the incident *doesn't* explain is a listed section, not a
  discount: folding "we could not see the relay" into a smaller number would
  tell a reader we were less sure and never tell them of what.
- **`Basis.INFERRED` is a field and a rendered sentence**, interpolated with
  the surfaces no edge was found between and stating what inference costs ("can
  be wrong in ways a declared dependency edge cannot"). A canned sentence stops
  being read after the second report. `Basis.TRAVERSED` exists so a stored
  incident can say which kind of claim it is; a test pins that nothing here can
  emit one.
- **Three statuses again.** `UNCORRELATED` ("we got an answer, it tied
  nothing") never collapses into `UNAVAILABLE` ("we could not get an answer") —
  an operator told "uncorrelated" concludes we checked. An unestablished
  candidate still returns an incident listing every surface as unexplained: the
  faults were real and simultaneous, and returning nothing would erase that.
- **No new prompt.** The diagnosis prompt already asks for one causal
  hypothesis over a pile of evidence, which is the question correlation needs;
  a second would be a second thing to keep grounded and a second
  `PROMPT_VERSION` to keep honest, for nothing.
- **All ten guards mutation-checked**, not assumed from a green first run —
  each inversion (cross-surface requirement, blind-as-leg at both stages,
  cluster gap, `MIN_CORRELATED_SURFACES`, the UNAVAILABLE/UNCORRELATED split,
  the ungrounded branch, unexplained-dropping, the zero-confidence render, the
  `Incident` invariant) broke a specific named test. `PYTHONDONTWRITEBYTECODE=1`
  throughout, per the stale-`.pyc` trap recorded under DM1.6.
- **One trap found and closed while doing it:** the two "grounded but still
  uncorrelated" tests would also pass if the evidence-id scheme drifted, since
  an ungrounded answer yields `UNCORRELATED` too — they would then prove only
  that a broken citation is rejected, which is another layer's test. Both now
  assert the fixture is `GROUNDED` first. `test_diagnose.py`'s id pin only
  covers the disk and Metricool ids, not `sms:relay`'s.
- Files: `src/deadman/correlate/{__init__,window,incident,engine,report}.py`,
  `tests/test_correlate_{window,engine,incident,report}.py`, one recording
  (+ README section), `docs/ARCHITECTURE.md`.
- Gates: `pytest tests/` 192/192 (up from 158); `ruff check .` clean;
  `bpsai-pair arch check --strict` clean.
- **Not wired into `service.py`, same reason as DM1.6.** Correlation needs a
  model client and the endpoint holds no credentials. DM1.12 is the call site
  that has both; `report.as_dict` is board-shaped and ready for it.

### Session: 2026-08-11 — DM1.6 remediation registry and executor (`/start-task DM1.6`)

- **The question this turned on:** the diagnosis is a hypothesis in *prose*, so
  what does "selection keys on the diagnosis" mean without the model's words
  becoming the key? The answer taken here splits the decision in three, and the
  seam is the whole design:
  - **which evidence rows are causal** — the model. That is inference over
    messy heterogeneous failure material, the part a rule engine cannot do.
  - **what those rows mean** — `remediate/cause.py`, rules written in advance,
    reading only material probe code wrote (status codes, error codes,
    probe-authored summaries), returning a value from a closed `Cause` enum.
  - **what to do about it** — `remediate/registry.py`, a table from `Cause` to
    a function that existed before the run.
  No string a model produced is ever a key, an argument, or a body. A
  hallucinating model can push selection toward the wrong *registered* action;
  it cannot reach an action nobody wrote.
- **The test that makes the AC real** is a bundle, not an assertion.
  `tests/recorded/bundle-metricool-publish-failure.json` holds one fault class —
  a scheduled post absent at the destination — with four candidate causes beside
  it. Four recordings cite different rows of it, so the fault is held constant
  and only the diagnosis varies: `retry-now` vs `refresh-credential` vs
  escalate. `grounded-expired-credential` is deliberately adversarial — fully
  grounded, every cited fact checks out, and its prose says in plain English to
  "retry ... and re-queue the post right away". No retry is selected, because
  selection reads the cited evidence and not the sentence.
- **Precedence, because two causes can be true at once.** A diagnosis citing a
  503 *and* a lapsed token would earn a retry on the first and be doomed by the
  second. `PRECEDENCE` orders causes by how harmful acting on a lower one is
  while a higher holds, and is asserted total over `Cause` — a missing member
  would sort arbitrarily, which is exactly how a retry sneaks ahead of a
  credential failure.
- **Causes with no action, on purpose.** Policy refusal and disconnected
  channel are classified confidently and have nothing registered against them:
  re-queueing a post the platform refused burns rate limit against a decision
  already made, and re-sending to an unwired channel succeeds locally and
  delivers nothing. Six refusal branches in `Executor._refusal` in all —
  diagnosis not grounded (covering both `UNGROUNDED` and `UNAVAILABLE`), cited
  evidence unresolvable, failure unrecognised, no action registered, confidence
  under floor, capability unwired — each with a test.
- **The confidence cap from DM1.5 now does work.** Every action floor sits
  above `Method.REPORTED`'s 0.4 ceiling, asserted as an invariant, so a
  hypothesis leaning on a scheduler's "it published fine" can never move
  infrastructure however confidently phrased. `grounded-disk-cascade` claims
  0.7, is capped to 0.4, and escalates.
- **Dry run is the default** — a wet run has to be asked for, and the plan is
  the same object either way (asserted by equality), so a rehearsal is a
  rehearsal rather than documentation. `ActionResult` carries `performed`, never
  `success`, with a test pinning the field set: whether the surface recovered is
  a fact about the surface, and that is DM1.7's to establish.
- **Every one of the eight behaviours was mutation-checked** rather than
  assumed from a green first run — the suite passed 40/40 on the first
  execution, which is precisely when a test file deserves suspicion. Inverting
  each guard in turn (precedence order, 429-as-transient, classifying
  healthy/blind rows, ignoring `dry_run`, dropping the `is_actionable` gate,
  dropping the confidence floor, dropping the capability check, skipping the
  generated-body guard) broke a specific named test each time. Worth recording
  from that exercise: a pure-reorder mutation is the same file size, and if the
  edit and the restore land in the same second Python reuses the stale `.pyc` —
  one "clean" run was in fact still executing mutated bytecode. Purge
  `__pycache__` or set `PYTHONDONTWRITEBYTECODE=1` when mutation-testing.
- Files: `src/deadman/remediate/{__init__,cause,registry,actions,executor}.py`,
  `tests/test_remediate_{cause,selection,executor}.py`, one bundle and five
  recordings under `tests/recorded/` (+ README), `docs/ARCHITECTURE.md`.
- Gates: `pytest tests/` 158/158 (up from 117); `ruff check .` clean;
  `bpsai-pair arch check --strict` clean.
- **Not wired into `service.py` yet, deliberately.** DM1.7 is the natural call
  site — it re-observes after a remediation, and an executor plumbed into the
  board without it would report actions taken with nothing checking whether
  they helped, which is the heartbeat problem this project argues against.
  `Capabilities` is the injection point: all three are optional, default to
  absent, and an unwired capability escalates rather than planning around
  itself. Nothing real is wired to anyone's infrastructure yet.

### Session: 2026-08-11 — DM1.5 diagnosis layer on Gemini via ADK (`/start-task DM1.5`)

- The design question this task actually turned on: *what does "the model may
  not assert a fact it wasn't given" mean when the model's output is prose?*
  The answer taken here is to stop treating the response as one thing. A
  response has **facts** and it has **inference**, they get different fields,
  and only one of them is believed.
  - `citations` — each is `{evidence_id, quote}`, and the quote must appear
    **verbatim** (case/whitespace normalised only) in the *specific* evidence
    it names. Checked per-evidence rather than against the whole pile, because
    attributing the scheduler's 500 to the disk read is a causal claim and
    letting it through because the string exists *somewhere* would smuggle the
    interesting part of the reasoning past the check.
  - `hypothesis` — free prose, allowed to be new text, which is the entire
    reason a model is in this pipeline rather than a rule engine.
- **Rejection is all-or-nothing, deliberately.** One invented fact among four
  good citations discards the whole answer, because the hypothesis was
  reasoned from the invented fact along with the rest — salvaging the
  survivors leaves a conclusion standing on a premise that was thrown out.
  The planted-fabrication recording is built this way on purpose (one real
  citation, one invented) since a wholly fabricated response is the easy case.
- **Three statuses, mirroring `Observation`.** `GROUNDED` /
  `UNGROUNDED` ("the model said something false") / `UNAVAILABLE` ("we could
  not read what it said"). The last two are never collapsed: one is a fact
  about the response, the other a fact about our own blindness, and a report
  that conflates them tells an operator to distrust a model that may have been
  fine. `DiagnosisEngine` never raises and never returns `None` — same
  contract as `run_probe`, one layer up.
- **Confidence is capped, not accepted** (beyond the literal AC, kept because
  it is the difference between confidence being a number the model made up and
  one the system stands behind). The weakest cited evidence sets the ceiling
  off `Method`'s existing trust ordering — `REPORTED` caps at 0.4, a blind
  citation caps at 0.5. The flagship recording claims 0.7 leaning partly on a
  scheduler report and lands at 0.4; `claimed_confidence` is kept alongside,
  since the gap is itself a signal. A test asserts the cap does *not* bind on
  strong evidence, so it stays meaningful rather than a blanket haircut.
- Four evasion routes are tested and all fail closed: fabricated quote; quote
  lifted from a *sibling* evidence row; hallucinated surface; and an evidence
  id smuggled into the prose while every citation is legitimate — that last
  one passes a citations-array-only check, which is why the prose is scanned
  too. Plus: no citations at all, confidence outside `[0,1]`, unreadable
  response, model down, and an empty bundle (which never reaches the model —
  with nothing to reason over, anything said is invention).
- **Known limit, stated rather than papered over** (`grounding.py`, "Where the
  enforcement ends"; also `docs/ARCHITECTURE.md`): arbitrary unsupported prose
  *inside* the hypothesis cannot be detected deterministically. The defence is
  structural, not detective — the hypothesis is never rendered or consumed as
  fact, carries capped confidence, and DM1.6 selects deterministic code off
  the diagnosis. A fabricated sentence is visible to a human and inert to the
  machine, which is the most this boundary can honestly claim.
- Files: `src/deadman/diagnose/{schema,grounding,prompt,engine,gemini}.py`,
  `tests/{test_diagnose,test_diagnose_grounding,recordings}.py`,
  `tests/recorded/` (8 recordings + README), `docs/ARCHITECTURE.md`,
  `pyproject.toml`. Split beyond the brief's two modules to stay inside
  `arch check --strict`'s function/file limits and to keep grounding
  independently testable from the engine.
- `PROMPT_VERSION` is made honest by pinning `prompt_fingerprint()` in a test:
  editing the instructions without bumping the version fails the suite, so a
  diagnosis recorded last week can still be explained by the prompt that
  produced it.
- Gates: `pytest tests/` 117/117 (up from 61); `ruff check .` clean;
  `bpsai-pair arch check --strict` clean.
- **Carried into DM1.6/DM1.12, needs a human with GCP access:** the ADK call
  shape in `gemini.py` is the one unexercised code path. No `google-adk` and
  no GCP credentials exist here (same constraint as the DM1.8 blocker), so it
  is written to the documented ADK interface and flagged with a `.. warning::`
  naming the exact smoke test. Contest eligibility depends on a real Gemini
  call happening at least once — see What's Next #1. Everything the model
  touches downstream is model-agnostic and fully covered offline, so the smoke
  test is the only thing that gap blocks.

### Session: 2026-08-11 — DM1.9 SMS relay probe with active canary (`/start-task DM1.9`)

- `src/deadman/probes/sms_relay.py`: `SmsRelayProbe`, built on the same
  never-passive principle as Metricool — silence on this rail is
  structurally ambiguous (no traffic vs. dead rail look identical), so the
  probe never infers health from quiet and instead dispatches its own
  `Method.ACTIVE_CANARY` and reads the result back.
  - Dispatch acceptance (`DispatchOutcome.ACCEPTED`) is treated the same way
    Metricool treats a scheduler report: a claim, not evidence. `HEALTHY`
    requires `SentFolderReader.find(token)` to confirm the canary landed;
    accepted-but-never-landed is `FAULT` ("dead rail"), not silence.
  - `DispatchOutcome.UNREACHABLE` (can't reach the relay host at all) →
    `UNOBSERVABLE`, same treatment as any broken instrument — it says
    nothing about the relay itself. `DispatchOutcome.REJECTED` (host
    answered and explicitly refused the send) → `FAULT`, real evidence the
    relay is broken. Both carry a `detail["dispatch_outcome"]` tag so a
    report can tell them apart.
  - Cadence: canaries are real, billable sends against a real carrier, so
    the probe records each attempt to a `history_path` (append-only jsonl,
    same pattern as `disk.py`'s trend history) and only fires a fresh
    canary once `cadence_hours` has elapsed since the last one —
    `DEFAULT_CADENCE_HOURS = 12.0`. Inside the window, `observe()` returns
    `UNOBSERVABLE`, never `HEALTHY`: no fresh canary this sweep means no
    fresh evidence, full stop. Attempts are recorded even on
    unreachable/rejected outcomes so a persistently broken relay isn't
    hammered every sweep.
- `tests/test_probe_sms_relay.py`: 14 tests, no live network (hermetic
  `conftest.py` blocks sockets suite-wide; no `allow_network` marker used).
  Covers: canary confirmed → `HEALTHY`; unreachable host → `UNOBSERVABLE`
  (never `FAULT`); rejected send → `FAULT`, distinct from unreachable in
  `detail`; not-due-yet → `UNOBSERVABLE` (never `HEALTHY`) with zero calls
  to the relay or sent folder; first-ever call (no history) still sends;
  cadence is configurable and the default is conservative (≥6h); accepted
  but absent from the sent folder → `FAULT` naming the token; an
  unreachable attempt still records and throttles the next call; raising
  relay/sent-folder readers degrade to `UNOBSERVABLE`, never `FAULT`,
  both directly and through `run_probe`; surface id (`sms:relay`) is
  stable. Suite now 61/61 (up from 47). `ruff check` and
  `bpsai-pair arch check --strict` both clean.
- Did not reuse `deadman.probes.destinations` (the prior session's note in
  What's Next) — that module is specifically for reading social-platform
  permalinks (X/Instagram/etc.), and has no relevance to an SMS relay's
  sent folder. The reusable idea that *did* carry over is the shape of the
  contract: a weak self-reported "accepted" tier that can never alone
  produce `HEALTHY`, mirroring Metricool's `Method.REPORTED` scheduler
  claim.

### Session: 2026-08-11 — DM1.8 Cloud Run service, blocked on live deploy (`/start-task DM1.8`)

- Built everything locally verifiable, TDD throughout, and stopped short of
  the one step this sandboxed environment structurally cannot do: an actual
  `gcloud` deploy. That is a real, billable, hard-to-reverse action against
  live external infrastructure requiring credentials this session does not
  have — the honest outcome is `blocked`, not a fabricated URL.
- `src/deadman/service.py`: a dependency-free WSGI app (`make_app`/`app`)
  publishing the current board — `sweep()` + `blind_spots()` over probes
  that need no secrets (`DiskProbe`, `MorningBriefProbe`, paths from
  `DEADMAN_DISK_HISTORY`/`DEADMAN_BRIEF_LOG` env vars). A raising or
  malformed probe becomes a blind-spot row, never a 500, per the base
  contract. `tests/test_service.py`: 8 tests, board assembly and the WSGI
  app exercised in-process (fake `environ`/`start_response`, no sockets) —
  suite now 47/47 (up from 39).
- `Dockerfile` + `.dockerignore`: installs the zero-dependency package and
  runs `python -m deadman.service`. **Actually built and run locally** —
  `docker build` succeeded, `docker run` + `curl` returned the board as
  JSON (200), disk probe `healthy`, morning-brief probe correctly
  `unobservable` (no log mounted in the container) — proving the board's
  honest-blind-spot behavior survives containerization. Image removed after
  verification; this was possible only because this Mac's Docker daemon
  turned out to be working again (the sprint brief's "corrupted" note is
  stale) — the deploy path itself still goes through Cloud Build regardless,
  per the AC.
  `cloudbuild.yaml`: build/push on `gcr.io/cloud-builders/docker` (Cloud
  Build's own worker, never local), deploy via
  `gcr.io/google.com/cloudsdktool/cloud-sdk`. Structure validated with
  `yaml.safe_load`.
- `infra/README.md`: project setup, API enablement (`cloudbuild`, `run`,
  `artifactregistry`), the `gcloud builds submit` deploy command, URL
  lookup, curl verification, the env var table, and an optional
  local-Docker sanity-check path.
- **Blocked, not done — see Blockers.** Checked this environment for any
  path to a live deploy before declaring the blocker: no `gcloud` binary on
  `PATH`, no `~/.config/gcloud`, no SDK under `~/google-cloud-sdk` or
  Homebrew casks. Outbound network from this sandbox is actually live
  (confirmed via a raw socket connect), so the gap is tooling/credentials,
  not network egress. `bpsai-pair task update DM1.8 --status done` correctly
  refused on the two live-deploy AC items; task set to `blocked` rather than
  forced through.
- Gates run on everything that doesn't require GCP: `pytest tests/` 47/47;
  `ruff check .` clean; `bpsai-pair arch check --strict` clean.

### Session: 2026-08-11 — DM1.4 Metricool probe + verification spike (`/start-task DM1.4`)

- **Spike first, and it came back negative on the primary destination.** Live
  unauthenticated `curl` against real posts versus fabricated ids, three user
  agents. The test that mattered was not "does a permalink return 200" but
  "does the response discriminate present from absent", and for Instagram it
  does not: a real famous public post and a nonexistent shortcode both return
  **200** with the same `"pageID":"httpErrorPage"` shell and no `og:` tags. The
  shortcode in the body is the request URL reflected back. `instagram_oembed`
  returns the identical 400 "Media Not Found" for the real post without an
  approved Meta app, and that approval is unavailable — so the API answer is
  not "harder", it is "no". Facebook returns 400 for everything including real
  pages. **X discriminates** (200 vs 404, stable over 3 real + 3 fake ids ×2
  passes and 10 consecutive requests) and its 200 even carries the post text in
  `og:description`, so it supports content-level confirmation.
- **Consequence, taken honestly rather than engineered around:** the chosen
  path is `Method.DESTINATION_PUBLIC` (trust tier 3 of 5) and it only exists
  for X. Instagram posts yield `UNOBSERVABLE` **forever** — a declared blind
  spot that gets its own line via `blind_spots()`, which is strictly better
  than the fabricated `HEALTHY` that let the original FWDAO incident run
  unnoticed. Both false directions were live and were rejected: keying on
  status would report every missing post as published, keying on the error
  marker would report every published post as missing.
- `src/deadman/probes/destinations.py`: `PLATFORM_VERIFICATION` (X/Twitter
  verifiable; Instagram, Facebook, Threads, LinkedIn not; unlisted fails
  closed), `DestinationState`, `DestinationRead` carrying its own `Method`, and
  `PermalinkReader` with an injected transport. The reader **refuses to fetch an
  opaque platform** even if wired directly, because `200 → PRESENT` on
  Instagram manufactures the exact false pass this project exists to catch.
- `src/deadman/probes/metricool.py`: `MetricoolProbe` verifies every post
  Metricool reports published. Precedence is tested, not incidental — one
  confirmed absence carries the batch to `FAULT` naming the post ids (plus
  `absent_permalinks`); a known fault is not downgraded by blindness on a
  sibling; one unverified post prevents `HEALTHY` for the batch. A 10-minute
  propagation grace period keeps a just-published post from being called absent,
  and an empty schedule is `UNOBSERVABLE`, not healthy.
- `tests/test_probe_metricool.py`: 20 tests, suite now 39/39 (up from 19).
  Scheduler and reader both injected, no `allow_network` marker, so zero network.
- Gates: `ruff check .` clean (two E501s fixed); `bpsai-pair arch check
  --strict` clean — the first draft tripped "too many functions" (16 > 15) and a
  file-size warning, which drove the split into `destinations.py` (platform
  knowledge, reusable by DM1.9's canary) and `metricool.py` (batch reasoning).
- Follow-ups recorded in the doc: one fetch of a real LinkedIn activity URN
  settles whether it joins the verifiable set; prefer verifiable destinations on
  the FWDAO calendar where content allows; re-run the spike before the demo,
  since every finding is a fact about someone else's server.

### Session: 2026-08-11 — DM1.3 brief + disk probe tests (`/start-task DM1.3`)

- `tests/test_morning_brief_probe.py`: missing log inside an existing
  directory yields `FAULT`; a missing *parent* directory yields
  `UNOBSERVABLE` (config problem, not the brief's fault); a file with a
  fresh mtime but a stale timestamp inside its last row still yields
  `FAULT` (explicitly asserts the mtime *is* fresh, to prove the probe
  isn't using it); a torn final JSONL row falls back to the newest
  parseable row before it (asserted via the fallback row's timestamp and
  `row_count == 2`, not just "didn't error"); a future-dated timestamp
  yields `UNOBSERVABLE` (clock skew, not a verdict).
- `tests/test_disk_probe.py`: mocks `shutil.disk_usage` and pre-seeds
  `DiskProbe`'s history JSONL to control the trend independently of the
  live volume. A perfectly linear -20GB/day slope with 50GB currently free
  (well above a 10GB floor) still yields `FAULT` because the 2-day runway
  is inside the 14-day window — the "healthy level, bad trend" case this
  probe exists for. A single sample yields `HEALTHY` with
  `detail["trend"] == "insufficient history"` and no `slope_gb_per_day`
  key. A 5-point series with one mid-series outlier (40GB dip amid
  ~80GB) keeps a non-negative least-squares slope and stays `HEALTHY` —
  proving the outlier doesn't flip the projection.
- Verification: `pytest tests/` — 19/19 passing (up from 11); `ruff check .`
  clean repo-wide. Built a scratch `python3.11` venv (`pyproject.toml`
  requires 3.11+; the ambient `python3` was 3.14) since none existed in the
  worktree yet.
- All 9 acceptance criteria checked off in `.paircoder/tasks/DM1.3.task.md`
  with the specific test (or command) that satisfies each; `bpsai-pair task
  update DM1.3 --status done` passed the strict AC gate on first attempt.

### Session: 2026-08-11 — DM1.2 evidence model + probe contract tests (`/start-task DM1.2`)

- The evidence model (`src/deadman/evidence/model.py`) and probe contract
  (`src/deadman/probes/base.py`) were already implemented as part of DM1.1's
  foundation work; this task locked their behavior down with tests rather
  than writing new implementation.
- `tests/test_evidence_model.py`: `Method` trust ordering (`DESTINATION_API`
  outranks `REPORTED`), `Evidence.provenance_row()` returns
  `(source, method, surface, iso_timestamp)`, `unobservable()` puts the
  reason in `detail` and merges any extra detail kwargs alongside it.
- `tests/test_probe_contract.py`: a raising probe yields `UNOBSERVABLE`
  (never `FAULT`) via `run_probe`; a probe returning a non-`Evidence` value
  is contained the same way; a well-behaved probe's evidence passes through
  unchanged; `sweep()` isolates one raising probe from the rest instead of
  taking the whole run down; `blind_spots()` returns only unobserved
  evidence and excludes healthy/fault entries.
- Verification: `pytest tests/` — 11/11 passing (up from 2 pre-existing
  hermetic-suite canaries); `ruff check` clean on both new files; `bpsai-pair
  arch check --strict` clean project-wide.
- All 7 acceptance criteria checked off in `.paircoder/tasks/DM1.2.task.md`
  with the test that satisfies each; `bpsai-pair task update DM1.2 --status
  done` passed the strict AC gate on first real attempt (after checking the
  boxes — the gate reads them from the task file, not from having tests
  merely exist).

### Session: 2026-08-10 — DM1.1 packaging, hermetic suite, CI (`/start-task DM1.1`)

- `pyproject.toml` (Python 3.11+, `deadman` package under `src/`) and
  `constraints.txt` pinned from a real resolve in a `python3.11` venv.
- `tests/conftest.py`: autouse fixture patches `socket.socket.connect` to
  raise `NetworkBlockedError` for every test; the `allow_network` marker
  (registered in `pyproject.toml`) is the only escape hatch, restoring the
  real `connect`.
- `tests/test_suite_is_hermetic.py`: two canary tests, both exercising the
  real socket layer rather than mocks — one asserts a real outbound attempt
  is blocked, the other (marked `allow_network`) asserts a real OS-level
  socket error comes through and is *not* `NetworkBlockedError`.
- Fixed the two defects flagged during planning: removed the unused
  `timedelta` import in `morning_brief.py` (F401), added `__init__.py` to
  `deadman/`, `deadman/probes/`, `deadman/evidence/`.
- `.github/workflows/ci.yml`: pytest, ruff check, `bpsai-pair arch check
  --strict` on push/PR to any branch.
- Wiring `arch check --strict` into CI surfaced two pre-existing violations
  (not introduced this session): `DiskProbe.observe` (77 lines) and
  `MorningBriefProbe.observe` (86 lines), both over the 50-line function
  limit. Split each into `observe()` + a `_trend_result`/`_age_result`
  helper — pure extraction, no behavior change, both probes' full test
  coverage is still DM1.3's job, not this task's.
- `.gitignore`: generalized `.venv-*` glob, added build output
  (`dist/`, `*.egg-info/`, cache dirs) and probe history artifacts
  (`*-history.jsonl`).
- Full CI job simulated locally end-to-end in a clean `python3.11` venv
  against the pinned constraints: pytest, ruff check, and
  `bpsai-pair arch check --strict` all pass.

### Session: 2026-08-10 — DM1 planning (`/pc-plan`)

- Read `plans/backlogs/DM1-deadman-v1.md` and `docs/SPRINT-BRIEF-DM1.md`.
- Registered all 12 tasks against the existing plan record and wrote full task
  bodies to `.paircoder/tasks/DM1.*.task.md` — objective, files, TDD-ordered
  implementation plan, acceptance criteria (backlog ACs plus wiring ACs for
  call site / configuration / failure modes), and verification commands.
- Resolved each `model:` via `bpsai-pair calibration recommend-model`
  (doctrine table; calibration store has insufficient samples). Deviations from
  the doctrine pick, all escalations: DM1.1 sonnet over haiku (foundation task,
  hermetic-suite canaries); DM1.4 and DM1.6 opus over sonnet (per backlog —
  spike judgment, and diagnosis-keyed action selection); DM1.12 opus over the
  backlog's sonnet (doctrine cross-module escalation, integration gate over all
  11 tasks).
- Marked DM1.8 `privileged: true` — live GCP infra and credentials.
- Found two concrete foundation defects while reading the existing source, both
  folded into DM1.1's plan: `src/deadman/probes/morning_brief.py:28` imports
  `timedelta` unused (F401 — fails the first CI ruff run), and `src/deadman/`
  has no `__init__.py` at any level despite `from deadman.*` imports.
- Gates run: `bpsai-pair validate` passed; `budget check` ok on every task
  (~2% of context each); `plan estimate` 297,750 tokens; `plan feasibility`
  REFUSED on DM1.1, DM1.2, DM1.5.
- Planned DM2: 9 task files materialized from plans/backlogs/DM2-make-it-real.md into plan-2026-08-dm2-make-it-real
- Planned DM2C: registered DM2C.1/DM2C.2 on plan-2026-08-dm2c-close, task files materialized with code-anchored implementation plans


## What's Next

**Now.** DM2C is complete — both tasks `done`, branch `engage/dm2c-close`
green and ready to merge to `main`. Merge it, then redeploy so the served
revision carries DM2C.1's `reported_by`/`held_since` (the current live
revision is `86c3662`, which predates them, and the committed board capture
records that honestly).

**Then, and only Kevin can do these:**

1. **Record the demo.** `docs/DEMO.md` is the run sheet: pre-flight checks
   first, then seven beats, one unedited take, Google Cloud visible on
   screen. Re-read the contest rules page immediately before recording —
   this session could not reach the network to re-verify them.
2. **Submit to Devpost**, and **make the repo public** (still private, and
   it cannot be judged that way).

Backlog decision 4 is now discharged: the morning brief may heal at any
6:00am run, and it no longer matters. `tests/fixtures/real-board-capture.json`
holds the live FAULT beside `collector:kevin-mac`, captured while it was
still true, and `docs/PROOF.md` is written from that rather than from the
live board.

**Kevin still owes** (unchanged): the demo video recording (with DM2C.2's
run sheet), the Devpost submission, and repo sharing with the judge
addresses. Deadline 2026-08-31 5:00pm PDT.

<details>
<summary>Superseded DM2-era notes (DM2.6/DM2.7 unblock instructions — both
since closed; kept for the runbook pointers)</summary>

**DM2.7** needed a real SMTP account; closed 2026-08-12 — the ops rail
worked all along (the "DUMMY SMTP" label was stale), two real messages
confirmed received. `docs/alerting.md` has the verification script.

**DM2.6** needed a `gcloud`-authenticated machine; closed 2026-08-11 —
scheduler job `deadman-self-check` created and verified by reading the
`self:sweep` row back out of Firestore. `infra/scheduler.md` remains the
runbook of record.

</details>

DM2.6 inherited one change from DM2.5 worth flagging: `infra/collector/
collectors.example.json` now declares **two** collectors (`kevin-mac` and
`kevin-rig`), not one — `DEADMAN_COLLECTORS` on the deployed service should
keep pointing at that same file rather than special-casing the Mac. This
session did not need to touch it.

What DM2.6 inherits from DM2.4, and must not undo:

- **`DEADMAN_COLLECTORS` has to be set on the deployed service**, or the
  board it schedules will keep serving `collectors_declared: 0` — a board
  that watches nobody's silence. The declaration lives at
  `infra/collector/collectors.example.json`; `infra/README.md`'s "Collector
  liveness" section has the `gcloud run services update` line. `cloudbuild.
  yaml` sets `DEADMAN_STORE_BACKEND` the same way and is the obvious place
  to add it.
- **`interval_seconds` in that file must match `StartInterval` in
  `infra/launchd/com.deadman.collector.plist`** (900 in both today). DM2.6
  is the task that decides estate cadence deliberately; whichever number it
  picks has to be changed in both files, and a collector reporting less often
  than its declaration says will fault at cadence + one missed run.
- **`build_app()` in `service.py` now constructs the store once** and hands
  the same instance to ingest and to liveness. A scheduled endpoint that
  builds its own store would report silence from a collector whose delivery
  the service had just accepted.
- **`scripts/mutation_check.py` must stay green** (`PYTHONDONTWRITEBYTECODE=1
  python scripts/mutation_check.py`). It is not wired into pytest — it mutates
  source files in place and restores them — so a refactor that moves a guarded
  line reports `SKIP` and a non-zero exit rather than passing quietly.

What DM2.5 inherits from DM2.3, and what DM2.3 actually built (superseding
the DM2.2-session notes below, which described the plan rather than the
result):

- **The collector is `src/deadman/collector/{config,transport,spool,run}.py`,
  done.** It signs with `deadman.ingest.wire.dumps` + `auth.sign` and posts
  to `POST /evidence` with the `X-Deadman-Signature` header, exactly as
  planned — but the freshness/spool interaction below was resolved
  differently than the plan implied: a spooled batch is **not** re-signed
  with its original `signed_at` before redelivery, because that would still
  read as stale after any outage longer than 5 minutes. `Collector._send`
  builds a **fresh `Batch`** — current clock, same evidence rows, same
  `read_at` — on every attempt, first send or the Nth retry. That is the
  actual mechanism DM2.6 (or any future caller) should reuse if it schedules
  the collector rather than calling `run_once` directly.
- **DM2.5's extension point is `PROBE_TYPES` in `collector/config.py`.**
  Adding a real surface (Metricool, SMS relay) that needs an injected client
  is not yet possible through a config file — only `DiskProbe` and
  `MorningBriefProbe` are registered, because both take plain arguments a
  JSON file can express. A probe needing a `SchedulerClient` or
  `RelayClient` needs either a registry entry that knows how to construct
  the client from config (e.g. an API key field), or a documented decision
  that those probes are wired by code, not by this collector's config file.
  Decide this explicitly in DM2.5 rather than discovering it mid-task.
- **DM2.4** reads `detail.collector_id` and `detail.received_at` off stored
  rows. `received_at` is the field that makes "this collector has gone quiet"
  answerable; `read_at` cannot, because it is the collector's own clock on an
  observation that may have been spooled. Note every ingested row is
  `Method.REPORTED` regardless of what the collector claimed — check
  `detail.reported_method` if the collector's own grade matters.
- **DM2.7** records transport failures through the same store. It is
  `blocked` on one AC — see Blockers.
- **Correction to the note left under DM2.1:** idempotent replay was *not*
  free from content-addressed `row_id`. An arriving row must carry an arrival
  time, which changes the hash on every delivery, so the store's dedupe would
  not have fired. Ingest dedupes on `detail.wire_row_id` instead — the row's
  identity computed *before* annotation.
- **Done, was DM2.1's handoff:** the Dockerfile installs `.[firestore]` and
  `cloudbuild.yaml` sets `DEADMAN_STORE_BACKEND=firestore`. **DM2.6 must
  verify on the first real deploy** that the Firestore database exists and the
  Cloud Run service account holds `roles/datastore.user`, and that
  `DEADMAN_INGEST_SECRET` is set on the service — all three are startup
  failures by design, so the deploy will fail loudly rather than serve wrong.
  See `infra/README.md`.

Items below are DM1-era and carried forward.

1. **DONE — both GCP items landed.** The deploy is live at
   https://deadman-mrapac5nda-uc.a.run.app and the live Gemini call has run
   (`gemini-3.5-flash` via ADK, structured `Diagnosis` with citations). Two
   findings from doing it, both recorded in `docs/gemini-verification.md`:
   `gemini-3.5-flash` is served **only from the `global` Vertex endpoint** and
   404s in `us-central1`, and a fresh service account returns 403 for about a
   minute before the IAM binding takes effect, which is indistinguishable from
   a missing role.

   Still open from that item: the recorded fixtures in `tests/recorded/` are
   still authored, not real captures. The smoke test proved the call shape but
   its raw response was not saved. Worth doing in DM1.12 so the offline tests
   replay something a real model actually said.
2. DM1.7 is done. `deadman.remediate.verify.verify_remediation(executor,
   probe, diagnosis, evidence, max_attempts=3)` is ready to be the loop
   DM1.12 wires in: it takes the same `Executor` and `Diagnosis`/`Evidence`
   DM1.6 already produces, plus the originating `Probe`, and returns a
   `VerificationOutcome` (`VERIFIED` / `NOT_ATTEMPTED` / `EXHAUSTED`).
3. DM1.10 is done. For DM1.12, `deadman.correlate` is the piece the demo wants
   on screen: `Correlator(diagnosis=DiagnosisEngine(client=...)).correlate(
   sweep(probes))` returns incidents, `correlate.report.render` prints the
   operator-facing text and `as_dict` the board row. It is the only layer that
   visibly does something a graph-based monitor cannot, so it belongs in the
   unedited take.
4. **DM1.11 is done.** `deadman-self-check` is the scheduler-facing command;
   `run_self_check(log, window_hours, channel)` is the callable, and
   `AlertChannel(transport, send, monitored)` is what DM1.12 must construct
   with the real monitored-surface list so the demo's alarm is genuinely out
   of band.
5. **DM1.12 (integration gate) is the only task left, and every dependency is
   `done`, so it can close for real rather than partially.** Three things it
   should pick up that are known and unresolved: the `tests/recorded/`
   fixtures are still authored rather than real Gemini captures; the deployed
   service's self-evidence does not survive a cold start (per-instance
   filesystem); and the live demo must run unedited per the rules, so the
   break-and-heal sequence needs rehearsing end to end against the deployed
   URL, not locally.
1. Start DM2.4 — collector liveness (absence must not read as health); DM2.5
   (real surfaces) is next after that, now that DM2.3 has unblocked it.
1. DM2C is done. Merge `engage/dm2c-close`, redeploy, then record the demo.


## Blockers

**0. RESOLVED — DM1.1's GitHub remote blocker.** `origin` now points at
`https://github.com/fivedollarfridays/deadman.git` and `bpsai-pair task show
DM1.1` reports `status: done`. The remote-creation decision this blocker was
waiting on was made outside this session; no action needed here.

**1. RESOLVED — DM1.8's live GCP deploy.** Project `deadman-20260810` was
created and gcloud installed on the rig, which is where the deploy ran from.
The service is live and public at https://deadman-mrapac5nda-uc.a.run.app and
DM1.8 is `done` with all six ACs verified.

Deploying it surfaced two defects in what the previous session had written,
both of which produce results that look fine: `cloudbuild.yaml` used
substitutions nested inside other substitutions, which Cloud Build does not
expand, and `--allow-unauthenticated` alone left the service returning 403
from the Google frontend while the build reported SUCCESS. Both are fixed and
documented in `infra/README.md`.

The lesson generalises past this task: `infra/README.md` documented a deploy
command that had never been run. The command was wrong. A runbook nobody has
executed is a hypothesis, and this project of all projects should not treat an
unexercised claim as evidence.

**2. `plan feasibility` REFUSES DM1.1, DM1.2, DM1.5** (fail-closed gate).
Reason: downstream token risk if a hub task fails — 422,500 tokens behind
DM1.1, 198,500 behind DM1.2, 151,500 behind DM1.5. The gate prescribes
inserting intermediate checkpoint/commit tasks. All three already end in a
verified-green commit by their own ACs, which is arguably the checkpoint the
gate is asking for. **Not overridden — an override is audited to
`bypass_log.jsonl` and is the user's call:**

```bash
bpsai-pair plan feasibility plan-2026-08-dm1-deadman-v1 --override "<reason>"
```

**3. Sprint is 345 Cx against a 300 Cx budget (~15% over).** Per the planning
skill's scope rule this is Epic-shaped; the plan record is currently a Story.
Either accept the overrun, cut from the list above, or re-scope to an Epic.

**4. DM2.7's "one real message is confirmed received" AC — needs a real SMTP
account, not more code.** Every other piece of DM2.7 is done: `EmailTransport`,
`email_transport_from_env`, `real_monitored_surfaces()`, `ThrottledAlertChannel`,
`record_transport_failures`, all tested and mutation-checked, `docs/alerting.md`
written. This is the one AC blocked on external state — `ops/.env`'s active
SMTP block is a labelled dummy (`# DUMMY SMTP — for T87.2 testing only. Real
sends will fail at connect`), and `ops/monitoring/alertmanager/alertmanager.yml`
independently confirms real email delivery isn't live there either (every
receiver is a `localhost` webhook, `# In production, add: Email` still a TODO).
ops carries its own backlog item for this
(`backlog-sprint-T152-outbound-email-rail.md`).

**Not overridden — needs one of two decisions:** wait for `T152` to land a
real ops SMTP account, or point `DEADMAN_ALERT_*` at any other working
account (e.g. a personal Gmail app password) in the meantime. Either way, the
verification is the one-time script at the end of `docs/alerting.md` — run
it, confirm the message lands, check the AC box, then `bpsai-pair task update
DM2.7 --status done` should pass immediately since nothing else is
outstanding.

**5. DM2.6's two live-infra ACs — needs a machine with `gcloud`, not more
code.** Every code AC is done: `POST /self-check` (`src/deadman/scheduled/`),
bearer-token auth mandatory at import (mirrors `DEADMAN_INGEST_SECRET`),
self-check evidence written through the DM2.1 store via
`StoreSelfEvidenceLog` (`src/deadman/self_check.py`), a test proving a second,
independently-built app instance reads what the first wrote (cold-start
survival), and the collector-vs-Cloud-Scheduler independence documented in
`infra/scheduler.md`. `pytest` 528/528, `ruff` clean both ways, `arch check
--strict` clean.

The two ACs this session could not close: **enabling the Cloud Scheduler API
and creating the job**, and **verifying the job fired at least once via a
stored row**. This sandboxed worktree has no `gcloud` CLI at all (`gcloud`:
command not found) and no Application Default Credentials
(`~/.config/gcloud` does not exist) — the same class of gap DM1.8's original
deploy blocker named ("a runbook nobody has executed is a hypothesis"), this
time because the tool itself is absent rather than the credential. Both ACs
have exact, reproducible commands written in `infra/scheduler.md` (API
enable, secret generation and `--update-env-vars`, `gcloud scheduler jobs
create http`, then `gcloud scheduler jobs run` plus a `FirestoreEvidenceStore`
read-back of the `self:sweep` surface to prove the row landed).

**Not overridden — needs one of two decisions:** run `infra/scheduler.md`'s
commands from a machine with `gcloud` authenticated for `deadman-20260810`
(the rig, per DM1.8's precedent — that deploy also had to run from the rig
because this environment lacked the tooling), or grant this environment
`gcloud` + ADC access. **One deploy-ordering hazard to act on before either
happens:** `deadman.service` now refuses to import without
`DEADMAN_SCHEDULER_SECRET` set, so the *next* `gcloud builds submit` must not
land until that variable is set on the live Cloud Run service via
`infra/scheduler.md`'s step 1 — merging this branch and redeploying before
setting it would take the currently-live service down entirely.
<!-- paircoder:state:end -->
## Quick Commands

```bash
bpsai-pair status
bpsai-pair plan show plan-2026-08-dm1-deadman-v1
bpsai-pair plan tasks plan-2026-08-dm1-deadman-v1
bpsai-pair plan feasibility plan-2026-08-dm1-deadman-v1
bpsai-pair task update DM1.1 --status in_progress
bpsai-pair task update DM1.1 --status done
```
