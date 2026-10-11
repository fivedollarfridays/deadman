# DM4 — One incident pages a few times, and the board shows only real surfaces

**Base:** main
**Summary:** durable escalating backoff for repeat alert emails, and removal of three clutter rows from the board

## Why this lane exists

From 2026-10-09 to 2026-10-11 one ongoing fault (`service:staging-queue`,
about 45 hours) produced 39 "deadman alert" emails, roughly one an hour, plus
one recovery notice. All of them sat unread. The earlier `cron:devpost` fault
produced 10 more in 10.5 hours. An alarm that repeats hourly teaches its owner
to ignore the thread, which is the failure this project exists to end.

Owner, 2026-10-11: "Stop the hourly repeat emails. One incident produced 39
emails, all still unread. Deadman should back off the way the ops freshness
monitor does (6 hours, 12, then 24) and keep the recovery notice." And:
"Clean up board clutter. host:disk/ reports the Cloud Run container's own
disk (1,001 GB free, 100 million days of runway), and self:sweep and
smoke:deploy-check show as undeclared surfaces."

**Known facts (2026-10-11, from origin/main at 92f4407 and the live board).**

- `src/deadman/scheduled/alerting.py` `evaluate()` fires on every sweep (every
  15 minutes, Cloud Scheduler) and relies on `ThrottledAlertChannel`
  (`src/deadman/remediate/transports.py`) to suppress repeats per
  `(key, state)`. `recover()` resets the throttle and sends one recovery
  notice if the surface had alarmed.
- The module docstring states the limit: "the throttle window lives in
  instance memory, so a Cloud Run cold start forgets it and a persisting fault
  may re-alert early ... a durable throttle is DM3 work if the repeats annoy
  in practice." They do. Any backoff measured in hours MUST survive a cold
  start, or it will not change what the owner receives.
- The reference behaviour is the ops freshness monitor: an alert when a
  surface goes newly bad, repeats on an escalating backoff of 6 h, then 12 h,
  then every 24 h while the episode stays open, and exactly one recovery
  notice when it heals. A change of alert state inside an episode (for
  example `stale` to `fault`) is a new fact and is never suppressed.
- The board's `held_since` / `held_seconds` are already walked from stored
  history, so the store can answer "since when has this surface been in this
  state".
- `host:disk/` on the live board is the in-container disk probe from
  `default_probes()` in `src/deadman/service.py`: "1001.9GB free, 100.0% free,
  103892339 days of runway". `infra/README.md` already tells readers to
  distrust it. The real disk is `host:mac/disk`, reported by the collector.
- Precedent for switching off a local probe on Cloud Run: deadman PR #20
  disabled the in-container morning brief probe through an empty
  `DEADMAN_BRIEF_LOG` environment variable.
- `undeclared_surfaces` on the live board is `["self:sweep",
  "smoke:deploy-check"]`. `self:sweep` is the service's own scheduled self
  check, written by the service itself. `smoke:deploy-check` is a leftover
  Firestore row from the 2026-08-11 end to end proof. `infra/scheduler.md`
  documents that exact list as expected output.
- The ops repo reads this board (`scripts/deadman_board_watch.py`): it uses
  the top level `self_check` object, each surface's `detail.last_report_at`
  for collector rows, and the fault / blind / healthy counts and problem
  summaries. Do not rename or remove any existing JSON field.

**Lessons already paid for in this repo (do not repeat).** In-process WSGI
tests and hand built fixtures have twice passed while production failed.
Build fixtures through the real renderers and the real store interface. A
module that is not called from the real sweep path is not done.

**Deploy is NOT part of this lane.** The orchestrator deploys from the rig
after merge. Never use `--set-env-vars` anywhere in docs or scripts; it wipes
the secrets. Use `--update-env-vars`.

**Secrets.** Never print, log or commit a secret or an env value. Tests use
fakes; no test sends mail or calls Google Cloud.

**Models.** DM4.1 changes the live paging path and must be wired and proven
end to end: `claude-opus-5`. DM4.2 is small but touches the public board:
`claude-sonnet-5`.

---

## Phase 1: Quiet alarm

### DM4.1 — A persisting fault repeats at 6 h, 12 h, then every 24 h, across cold starts | Cx: 8 | P0

**Description:** Replace the fixed in-memory repeat throttle with an episode
based, durable backoff. An episode opens when a surface first becomes
alertable, or when its alert state changes. The first alert of an episode
always sends at once. While the episode stays open in the same state, repeats
are due 6 h after the first alert, then 12 h after that, then every 24 h. A
state change inside an episode sends at once and restarts the schedule. When
the surface heals, exactly one recovery notice is sent and the episode
closes; a later fault is a new episode and sends at once. The record of what
was sent and when must live in the evidence store (or be derived from stored
history plus a stored record of sends), so a fresh instance with empty memory
makes the same decision as a warm one. A missed or late sweep must not lose a
due repeat: the decision is "is a repeat due and not yet sent", not "did a
threshold fall inside this sweep's window". If the store cannot be read to
make the decision, fail loud and send rather than stay silent. Repeat emails
say how long the surface has been in the state and when the next repeat is
due if it does not heal. Wire it into the real scheduled sweep path used by
`POST /self-check`, update the module docstring's "Known limit", and update
the docs that describe the throttle.

**AC:**
- [ ] Tests are written first and fail before the implementation (TDD)
- [ ] A surface in the same fault state across sweeps every 15 minutes for 48 hours produces alerts at 0 h, 6 h, 18 h and 42 h only (4 emails, where the old behaviour produced about 40)
- [ ] The same 48 hour run with a brand new alarm object and empty instance memory on EVERY sweep (a cold start each time) produces the same 4 emails, proven against the real store interface used in production, not a hand built fixture
- [ ] A state change inside an open episode alerts on that sweep and restarts the schedule
- [ ] Heal sends exactly one recovery notice; heal with no prior alert sends nothing; fault, heal, fault sends alert, recovery, alert with no suppression
- [ ] A sweep that arrives late (for example at 7 h after a missed 6 h mark) still sends the due repeat, once
- [ ] Two different surfaces in fault keep independent schedules
- [ ] If the send record cannot be read, the alert is sent and the failure is recorded as evidence, never swallowed
- [ ] The backoff schedule is one named constant, documented, and the repeat email states the held duration and the next repeat time
- [ ] The real sweep entry point (`POST /self-check` handler path) is exercised by a test that goes through the service's own wiring, showing the durable backoff is what production calls
- [ ] Existing alerting behaviour that is not about repeats is unchanged: out of band refusal, transport failure recorded as evidence and propagated, permanently blind local probe exemption
- [ ] Full suite green; ruff check and ruff format --check clean; `bpsai-pair arch check --strict` clean on touched files, with any file over the limit split

## Phase 2: Clean board

### DM4.2 — The board carries no in-container disk row and no false undeclared surfaces | Cx: 4 | P1

**Description:** (a) Make the in-container disk probe switchable the same way
PR #20 made the brief probe switchable, so the Cloud Run deployment can run
without `host:disk/` while local and test runs keep it by default. Name the
environment variable and its "off" value in `infra/README.md` with the exact
`gcloud run services update --update-env-vars` line the orchestrator will
run. With the probe off, the board must not show the row, must not count it
as a blind spot, and the alarm must not page about its absence. (b) A surface
the service itself owns and writes (`self:sweep`) is never listed in
`undeclared_surfaces`. (c) Find out whether any deploy or smoke script still
writes `smoke:deploy-check` on each deploy. If one does, change it to clean up
after itself or to use a declared surface. Either way, document in
`infra/scheduler.md` the one time removal of the leftover Firestore row
(remember the document id is percent encoded twice:
`smoke%253Adeploy-check`), and update the expected `undeclared_surfaces`
output there to `[]`. Do not delete the live row yourself; the orchestrator
does it after merge.

**AC:**
- [ ] Tests are written first and fail before the implementation (TDD)
- [ ] With the new variable set to its off value, `default_probes()` has no disk probe, the board JSON has no `host:disk/` row, `blind_count` is 0 for an otherwise healthy estate, and `evaluate()` fires nothing for it
- [ ] With the variable unset, behaviour is exactly as today
- [ ] `undeclared_surfaces` omits `self:sweep` and still lists a truly undeclared surface (proven with a stored row for some other surface)
- [ ] No existing board JSON field is renamed or removed; a test pins the top level keys and the `self_check` object's keys
- [ ] `infra/README.md` and `infra/scheduler.md` are updated as described, with `--update-env-vars` only
- [ ] The answer to "does anything still write smoke:deploy-check" is stated in the PR description with the file evidence
- [ ] Full suite green; ruff check and ruff format --check clean; `bpsai-pair arch check --strict` clean on touched files
