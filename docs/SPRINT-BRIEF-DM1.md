# Feature Brief: DM1 — deadman v1 (contest-ready)

## Idea

Build a silent-failure detection and remediation agent for heterogeneous
infrastructure. Four surfaces that fail quietly and share no schema: Metricool
posting, disk trend, the phone/SMS relay, and the morning brief cron. The
system detects deterministically, uses Gemini to diagnose *why* and choose the
right remediation, executes deterministically, then re-verifies against the
same capture-evidence standard.

Submission target: **All Things Agentic**, Taskmaster category, **deadline
Aug 31 2026 5:00pm PDT**. Solo. Hard platform requirements from the rules:
Gemini 3.5 Flash, one of ADK/GenAI SDK/Antigravity/GenKit, and at least one
Google Cloud infrastructure service, with visible proof it runs on GCP.

**Scope boundary:** this sprint ships a working demo of four surfaces end to
end. It does not ship the general surface registry, multi-brand support, or
retirement of the seven existing point-solution monitors. Those are v2.

## Codebase Context

- **Stack:** Python 3.11+, Gemini via ADK, Cloud Run + Cloud Build. No local
  Docker required (the Mac's daemon is corrupted; Cloud Build sidesteps it).
- **Size:** greenfield. 4 source files, ~600 lines, zero tests.
- **Already built (not tasks):** `evidence/model.py` (three-state observation,
  ranked evidence methods), `probes/base.py` (never-raise contract, blind-spot
  surfacing), `probes/morning_brief.py`, `probes/disk.py`.
- **Conflicting in-progress tasks:** none. Repo initialized today; validate and
  doctor both green.
- **Per this skill's own rule**, cross-task constraint detection is skipped:
  under 5 source files there is nothing to collide with yet.

## Sprint-Level Constraints

- **Hard external deadline, 21 days, three unfamiliar systems** (Gemini, ADK,
  GCP). The largest risk is the platform ramp, not the domain logic. **DM1.1
  and DM1.8 exist to retire that risk in week one.**
- **The rules gate eligibility.** No Gemini, no ADK, or no GCP service means
  ineligible regardless of quality. Those are P0 by rule, not by taste.
- **Cross-task contract edges:** `Evidence` (already built) is consumed by
  diagnosis, correlation and verification. `Diagnosis` (DM1.5) is consumed by
  remediation (DM1.6). `RemediationOutcome` (DM1.6) is consumed by the
  verification loop (DM1.7). Those contracts must land before their consumers,
  which is what drives the dependency graph.
- **Known unknown that can invalidate a task:** Metricool verification depends
  on reading the destination platform, and Meta approval looks unavailable.
  **DM1.4 opens with a spike** on whether a public permalink fetch returns
  200/404 reliably. If not, the surface drops an evidence tier or swaps
  platform. This must not discover itself in week three.

## Tasks

**DM1.1 — Foundation: packaging, hermetic test suite, CI**
- Cx: 25 · Priority: **P0** · Depends on: none
- Files: `pyproject.toml`, `constraints.txt`, `tests/conftest.py`,
  `tests/test_suite_is_hermetic.py`, `.github/workflows/ci.yml`, `.gitignore`
- AC template: gate
- Custom AC: sockets blocked for every test with an `allow_network` escape
  hatch; a canary test makes a real outbound call and asserts the block is
  live; `bpsai-pair arch check --strict` wired into CI; ruff pinned.

**DM1.2 — Tests for the evidence model and probe contract**
- Cx: 20 · Priority: **P0** · Depends on: DM1.1
- Files: `tests/test_evidence_model.py`, `tests/test_probe_base.py`
- AC template: refactor
- Custom AC: a probe that raises yields `UNOBSERVABLE`, never `FAULT`; a probe
  returning a non-`Evidence` value is contained; `blind_spots()` separates
  unobserved surfaces from healthy ones; method trust ordering asserted.

**DM1.3 — Tests for the two existing probes**
- Cx: 20 · Priority: **P0** · Depends on: DM1.1
- Files: `tests/test_probe_morning_brief.py`, `tests/test_probe_disk.py`
- AC template: refactor
- Custom AC: brief probe distinguishes missing-log-in-existing-dir (fault)
  from missing-dir (unobservable), ignores file mtime entirely, tolerates a
  torn final row. Disk probe fires on healthy level with bad trend, reports
  "no trend yet" on a single sample, least-squares slope resists one outlier.

**DM1.4 — Metricool probe + destination-verification spike**
- Cx: 35 · Priority: **P1** · Depends on: DM1.1
- Files: `src/deadman/probes/metricool.py`, `tests/test_probe_metricool.py`,
  `docs/metricool-verification.md`
- AC template: migration
- Custom AC: **spike first** — document whether the platform is readable via
  API, public permalink, or neither, and record the resulting evidence tier;
  scheduler-reported success alone never yields `HEALTHY`; a post reported
  published but absent at the destination yields `FAULT` naming the post.

**DM1.5 — Diagnosis layer (Gemini via ADK)**
- Cx: 40 · Priority: **P0** · Depends on: DM1.1, DM1.2
- Files: `src/deadman/diagnose/engine.py`, `src/deadman/diagnose/schema.py`,
  `tests/test_diagnose.py`
- AC template: schema
- Custom AC: consumes unstructured `Evidence.detail`; emits a typed
  `Diagnosis` with hypothesis, confidence, and the evidence ids it rests on;
  **the model never asserts a fact absent from the evidence**, enforced by a
  test that plants a fabricated claim; runs offline in tests via recorded
  responses.

**DM1.6 — Remediation registry and executor**
- Cx: 35 · Priority: **P0** · Depends on: DM1.5
- Files: `src/deadman/remediate/registry.py`,
  `src/deadman/remediate/actions.py`, `tests/test_remediate.py`
- AC template: schema
- Custom AC: action selection is a function of the **diagnosis**, not the
  fault (expired token must not re-queue; transient 5xx must); every action is
  deterministic code, never model output; a diagnosis with no matching action
  escalates rather than guessing; dry-run mode.

**DM1.7 — Verification loop: did the fix actually work**
- Cx: 25 · Priority: **P0** · Depends on: DM1.6
- Files: `src/deadman/verify/loop.py`, `tests/test_verify.py`
- AC template: gate
- Custom AC: re-runs the originating probe after remediation; success is a
  fresh `HEALTHY` observation, never the executor's return value; a fix that
  cannot be verified is reported unverified, not successful.

**DM1.8 — Cloud Run deployment via Cloud Build**
- Cx: 30 · Priority: **P0** · Depends on: DM1.1
- Files: `Dockerfile`, `cloudbuild.yaml`, `infra/README.md`,
  `src/deadman/service.py`
- AC template: gate
- Custom AC: builds with **no local Docker daemon**; deploys to Cloud Run;
  reachable endpoint returns the current board; satisfies the rules' "visible
  proof it runs on Google Cloud".

**DM1.9 — Phone/SMS relay probe with active canary**
- Cx: 30 · Priority: **P1** · Depends on: DM1.1
- Files: `src/deadman/probes/sms_relay.py`, `tests/test_probe_sms_relay.py`
- AC template: migration
- Custom AC: silence is explicitly ambiguous and resolved by canary, never
  assumed healthy; canary verified at the destination sent folder; canary
  failure distinguishes unreachable-host from send-rejected.

**DM1.10 — Cross-surface correlation**
- Cx: 30 · Priority: **P1** · Depends on: DM1.5, DM1.3
- Files: `src/deadman/correlate/engine.py`, `tests/test_correlate.py`
- AC template: schema
- Custom AC: concurrent faults across surfaces are offered as one incident
  with a hypothesised shared cause; **no lineage graph exists**, so the
  relationship is inferred from co-occurrence and evidence and the report says
  which; a single fault never invents a correlation.

**DM1.11 — Self-liveness and out-of-band alerting**
- Cx: 25 · Priority: **P1** · Depends on: DM1.8
- Files: `src/deadman/verify/self_check.py`,
  `src/deadman/remediate/alert.py`, `tests/test_self_check.py`
- AC template: gate
- Custom AC: deadman proves its own liveness from capture evidence it wrote,
  never a heartbeat; **alerts must not route through any monitored surface**
  (the brief could not report its own death for nine days for exactly this
  reason); no evidence at all exits non-zero.

**DM1.12 — Integration gate: demo, README, architecture diagram**
- Cx: 30 · Priority: **P0** · Depends on: all
- Files: `README.md`, `docs/DEMO.md`, `docs/architecture.png`,
  `sample-outputs/`
- AC template: gate
- Custom AC: **the demo must run live and unedited** per the rules; a scripted
  break-and-heal sequence rehearsed end to end; committed sample outputs
  regenerated by script, never hand-written; architecture diagram;
  reproducible setup verified on a clean clone.

## Dependency Graph

```
Wave 0:  DM1.1
Wave 1:  DM1.2   DM1.3   DM1.4   DM1.8   DM1.9      (depend only on DM1.1)
Wave 2:  DM1.5   (needs DM1.2)      DM1.11  (needs DM1.8)
Wave 3:  DM1.6   DM1.10             (need DM1.5)
Wave 4:  DM1.7   (needs DM1.6)
Wave 5:  DM1.12  (needs all)
```

## File Collision Matrix

| Wave | Tasks in parallel | Intersection |
|---|---|---|
| 1 | DM1.2, DM1.3, DM1.4, DM1.8, DM1.9 | **none** — separate test files, separate probe modules, infra files disjoint |
| 2 | DM1.5, DM1.11 | **none** — `diagnose/` vs `verify/self_check.py` + `remediate/alert.py` |
| 3 | DM1.6, DM1.10 | **none** — `remediate/registry.py`,`actions.py` vs `correlate/engine.py` |

`remediate/alert.py` (DM1.11) and `remediate/actions.py` (DM1.6) share a
package but not a file, and DM1.11 lands first. Neither edits `__init__.py`.

## Sprint Budget

- **Total Cx:** 345
- **Task count:** 12 — **P0:** 8 · **P1:** 4 · **P2:** 0
- **Over the ~300 Cx norm by ~15%.** Cut list, in order: DM1.10
  (correlation), DM1.9 (SMS canary), DM1.11 (self-liveness), DM1.4
  (Metricool). **Cut correlation first.** Cutting DM1.4 hurts most, since it
  is the surface with a real incident behind it and the strongest demo.

## Integration Points

- `Evidence` → consumed by DM1.5, DM1.7, DM1.10
- `Diagnosis` (DM1.5) → consumed by DM1.6
- `RemediationOutcome` (DM1.6) → consumed by DM1.7
- Probe instances (DM1.3, 1.4, 1.9) → re-run by DM1.7's verification loop
- Cloud Run service (DM1.8) → hosts everything; DM1.11 verifies it

## Out of Scope

- The general surface registry (adding a surface as config, not code) — v2
- Multi-brand support for Nick Cano or client brands — v2
- Retiring the seven existing point-solution monitors — v2, one at a time
- Any reuse of `ops`, `kai-studio` or Rail Agent **source**. The doctrine
  carries over and gets disclosed; not a line of code does.
- Fixing the Mac's Docker daemon. Cloud Build makes it unnecessary.
