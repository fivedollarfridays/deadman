# Current State

> Last updated: 2026-08-11

<!-- paircoder:state:begin -->
## Active Plan

**Plan:** `plan-2026-08-dm1-deadman-v1` — DM1: deadman v1 (contest-ready)
**Status:** Planned, not started
**Current Sprint:** DM1
**Backlog:** `plans/backlogs/DM1-deadman-v1.md`
**Brief:** `docs/SPRINT-BRIEF-DM1.md`
**Branch:** `engage/dm1-deadman-v1`

Silent-failure detection and remediation for heterogeneous infrastructure.
Submission target: All Things Agentic, Taskmaster category, **deadline
2026-08-31 5:00pm PDT**.

## Current Focus

DM1.1, DM1.2, DM1.3, DM1.4, DM1.5, DM1.6, DM1.7, DM1.9 and DM1.10 are `done`.
DM1.8 is `blocked` on a live GCP deploy step this session cannot perform (see
Blockers). DM1.11 still waits on DM1.8; **DM1.12 (integration gate) is the
only task left that isn't blocked on the GCP deploy**, though it depends on
all tasks including the blocked DM1.8/DM1.11.

**Spike result that changes the demo:** Instagram and Facebook destinations are
unreadable, so the Metricool surface is a declared permanent blind spot for
Instagram. X is verifiable. See `docs/metricool-verification.md`.

## Task Status

### Active Sprint (DM1) — 12 tasks, 345 Cx, DM1.1–DM1.7, DM1.9 and DM1.10 `done`

| ID | Title | Pri | Cx | Model | Depends on |
|---|---|---|---|---|---|
| DM1.1 | Packaging, hermetic test suite, CI ✓ | P0 | 25 | claude-sonnet-5 | — |
| DM1.2 | Evidence model + probe contract tests ✓ | P0 | 20 | claude-sonnet-5 | DM1.1 |
| DM1.3 | Brief + disk probe tests ✓ | P0 | 20 | claude-sonnet-5 | DM1.1 |
| DM1.4 | Metricool probe + verification spike ✓ | P1 | 35 | claude-opus-5 | DM1.1 |
| DM1.5 | Diagnosis layer on Gemini via ADK ✓ | P0 | 40 | claude-opus-5 | DM1.1, DM1.2 |
| DM1.6 | Remediation registry and executor ✓ | P0 | 35 | claude-opus-5 | DM1.5 |
| DM1.7 | Verification loop ✓ | P0 | 25 | claude-sonnet-5 | DM1.6 |
| DM1.8 | Cloud Run via Cloud Build ⚠blocked | P0 | 30 | claude-sonnet-5 | DM1.1 |
| DM1.9 | SMS relay probe with active canary ✓ | P1 | 30 | claude-sonnet-5 | DM1.1 |
| DM1.10 | Cross-surface correlation ✓ | P1 | 30 | claude-opus-5 | DM1.3, DM1.5 |
| DM1.11 | Self-liveness + out-of-band alerting | P1 | 25 | claude-sonnet-5 | DM1.8 |
| DM1.12 | Integration gate: demo, README, diagram | P0 | 30 | claude-opus-5 | all |

**Waves:** `DM1.1` → `DM1.2 DM1.3 DM1.4 DM1.8 DM1.9` → `DM1.5 DM1.11` →
`DM1.6 DM1.10` → `DM1.7` → `DM1.12`

**Cut list if over budget, in order:** DM1.10, DM1.9, DM1.11, DM1.4.

### Backlog

Out of scope for DM1 (v2): general surface registry, multi-brand support,
retiring the seven existing point-solution monitors.

## What Was Just Done

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

## What's Next

1. **Two things now need the same human with GCP access**, and they are worth
   doing in one sitting: (a) DM1.8's `gcloud builds submit --config
   cloudbuild.yaml .` per `infra/README.md`, reporting the deployed URL back;
   (b) one live Gemini smoke test through `GeminiClient` per the `.. warning::`
   in `src/deadman/diagnose/gemini.py`, to confirm the ADK call shape and to
   satisfy contest eligibility, which requires a real Gemini call. Save the raw
   response into `tests/recorded/` as a genuine capture and retire the authored
   one; nothing in the engine changes, it only ever sees a string.
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
4. DM1.11 (self-liveness) depends on DM1.8 and cannot start until the live
   deploy lands.
5. DM1.12 (integration gate) is now the only task not blocked by the GCP
   deploy that hasn't started — though its own AC depends on every task
   including the blocked DM1.8/DM1.11, so it cannot fully close either until
   that human-with-GCP-access session happens (see What's Next #1).

## Blockers

**0. RESOLVED — DM1.1's GitHub remote blocker.** `origin` now points at
`https://github.com/fivedollarfridays/deadman.git` and `bpsai-pair task show
DM1.1` reports `status: done`. The remote-creation decision this blocker was
waiting on was made outside this session; no action needed here.

**1. DM1.8 blocked on live GCP deploy — needs a human with `gcloud` access.**
This worktree/session has no `gcloud` CLI and no GCP credentials anywhere on
the machine (checked `PATH`, `~/.config/gcloud`, `~/google-cloud-sdk`,
Homebrew casks). Deploying is a real, billable, hard-to-reverse action
against live external infrastructure — not something to attempt without
explicit credentials and authorization, and not something faking a URL for
would satisfy honestly. All four other ACs are done and verified locally
(`Dockerfile` built and run with `curl` proving the board endpoint works
end to end in a real container; `cloudbuild.yaml` validated structurally;
`infra/README.md` written; `ruff`/`pytest`/`arch check` all clean). Task
status set to `blocked`. **Needs:** someone with GCP project access to run
`gcloud builds submit --config cloudbuild.yaml .` per `infra/README.md` and
report the resulting Cloud Run URL, after which the remaining two AC boxes
can be checked and DM1.8 closed.

**1. `plan feasibility` REFUSES DM1.1, DM1.2, DM1.5** (fail-closed gate).
Reason: downstream token risk if a hub task fails — 422,500 tokens behind
DM1.1, 198,500 behind DM1.2, 151,500 behind DM1.5. The gate prescribes
inserting intermediate checkpoint/commit tasks. All three already end in a
verified-green commit by their own ACs, which is arguably the checkpoint the
gate is asking for. **Not overridden — an override is audited to
`bypass_log.jsonl` and is the user's call:**

```bash
bpsai-pair plan feasibility plan-2026-08-dm1-deadman-v1 --override "<reason>"
```

**2. Sprint is 345 Cx against a 300 Cx budget (~15% over).** Per the planning
skill's scope rule this is Epic-shaped; the plan record is currently a Story.
Either accept the overrun, cut from the list above, or re-scope to an Epic.
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
