# Handoff — 2026-08-11

Written at the end of the session that finished DM1 and planned DM2. Read
`.paircoder/context/state.md` alongside this; that file is current and is the
project's own record. This one carries the things that live outside it:
decisions waiting on Kevin, risks that are not in any repo, and the reasoning
behind the DM2 plan.

## Where the project actually stands

DM1 is complete, 12 of 12 tasks, merged. 236 tests, ruff clean both ways,
`arch check --strict` clean apart from a pre-existing warning in bpsai-pair's
own `.claude/hooks/` scaffolding.

The service is live and public at **https://deadman-mrapac5nda-uc.a.run.app**,
project `deadman-20260810`, region `us-central1`. The deployed image tag is the
full commit SHA and currently matches `origin/main` exactly. Ask a running
service which commit it is:

```bash
gcloud run services describe deadman --region=us-central1 \
  --format='value(spec.template.spec.containers[0].image)'
```

**Deploy must follow merge.** Merging moves main and instantly makes the
deployed tag stale. That happened twice and both times the fix was to redeploy
from a clean clone of `origin/main`, never from a working tree.

## The honest assessment

DM1 produced something submittable. It did not produce something good yet, and
the gap is not cosmetic.

**deadman has never monitored anything.** Cloud Scheduler is not enabled on the
project. Nothing sweeps on a cadence. The service only runs probes when a human
sends it an HTTP GET. It is a library, a test suite, and an endpoint that
answers when poked.

**Nothing survives a cold start.** Evidence and self-liveness are written to
Cloud Run's per-instance ephemeral filesystem, so the deployed service proves an
instance's liveness rather than the service's.

**No surface watches real infrastructure.** Four probes exist. Zero are wired to
anything real.

**The demo's only breakable surface is a stub.** Honestly labelled, which is the
right call, but labelling a weakness does not remove it.

**The model fails to ground about 1 run in 4**, measured across only four runs,
so that number could be 10% or 40%. It is both a prompt quality problem and an
unmeasured one, and DM1 documented it instead of fixing it.

## The finding that reframes everything

During DM2 planning, `MorningBriefProbe` was pointed at
`~/ops/data/brief-send-log.jsonl` with no new code and immediately returned
FAULT.

**Kevin's morning brief has been dead since 2026-08-04 06:56.** Seven days,
undetected. `com.cognify.morning-brief` is loaded and fires daily at 6:00am;
`morning_brief_send.py` hangs, exceeds its 2700s deadline, and is killed by its
own hang guard. Last exit status 124. Confirmed in
`~/ops/api/logs/morning-brief-error.log`.

Nobody noticed because the brief is itself the alerting channel, so its death is
self-concealing. That is the exact sentence already written in
`src/deadman/probes/morning_brief.py`'s docstring, recurring in the estate it
was written from.

**The hang is an `ops` bug and has not been diagnosed.** Nobody has looked at
why the script blocks. Fixing it is separate work from deadman noticing it.

## Why DM2 is shaped the way it is

Planning found an architectural fact DM1 missed. **The surfaces are not where
the service is.** The brief log is on the Mac behind NAT. Disk matters on the
Mac and the rig. The phone relay is reachable over Tailscale from Kevin's
machines, not from Google's network. Cloud Run is structurally incapable of
reading any of it, and opening inbound access to a laptop is the wrong answer.

So DM2 is a topology change: a **collector** that runs where the surfaces live
and ships evidence to an authenticated ingest endpoint, and the hosted service
that stores, correlates and alerts. That is not a config task and it drives the
whole dependency graph.

Two constraints that only appear across tasks, both easy to miss task by task:

1. **A dead collector and a healthy estate produce the identical empty inbox.**
   Collector liveness is P0, not a nicety. It is this project's own three-state
   argument one level up, and it is explicitly not cuttable.
2. **Evidence crossing a wire must not have its method upgraded on arrival.** A
   report of a local reading is a weaker claim than the reading. Blurring that
   reintroduces the heartbeat this project exists to argue against.

Brief: `docs/SPRINT-BRIEF-DM2.md`. Nine tasks, 275 Cx, deliberately smaller than
DM1's 345 because DM2 carries infrastructure risk DM1 did not. One file
collision found and resolved by serialising DM2.8 behind DM2.6.

## Decisions waiting on Kevin

**1. The `ops` repo has 82 changed paths staged and uncommitted.** Includes the
bpsai-pair payload upgrade: new hooks, `CLAUDE.md`, `settings.json`,
`.paircoder/` config, plus deletions. This is the state an agent destroyed once
already; it survived only because it was recovered from a dangling commit.
Preserving it on a branch costs one commit. **Not done, because it is Kevin's
repo state and he had not answered.**

**2. Nobody has verified the actual contest rules.** Everything treated as a
platform requirement, Gemini 3.5 Flash via ADK plus one Google Cloud service and
"thirty percent for demo and production readiness", traces back to
`docs/SPRINT-BRIEF-DM1.md`, which Claude wrote from an earlier session's
reading. That is a summary, not a source. Web search budget was exhausted, the
guessed Devpost URL 404s, and nothing local records the rules. **Pull the real
criteria before optimizing for them.**

**3. Should the morning brief hang be diagnosed now or later?** It is Kevin's
actual daily tooling and it is broken today.

## Open items with no owner yet

- `fivedollarfridays/deadman` is **still private** and cannot be judged that way
- The **$25 GCP budget alert is unset**:
  https://console.cloud.google.com/billing/0148CA-176C18-47F84E/budgets
- The Vertex service account key at `~/.deadman-creds/vertex-sa.json` **on the
  rig** is a long-lived credential and should be deleted after the contest.
  Revocation commands are in `docs/gemini-verification.md`
- `docs/dm2-sprint-brief` also carries an unrelated bpsai-pair 2.42.0 config
  commit that a hook made, two files. Split it before merging
- Side branches hold engage residue from the failed DM1.1 run and are local
  only: `chore/dm1.1-close`, `engage/DM1.1-failed`, `engage/DM1.8-blocked`

## Gotchas that already cost real time

- **`gemini-3.5-flash` is served only from the `global` Vertex endpoint.** It
  404s in `us-central1`, where everything else deploys. Matching the location to
  the Cloud Run region silently costs you the required model.
- **A fresh service account 403s for about a minute** while its IAM binding
  propagates, which is indistinguishable from a missing role. Verify the binding
  exists, then wait, rather than changing permissions.
- **Cloud Build substitutions do not nest.** A `${PROJECT_ID}` inside another
  substitution's default reaches the builder as a literal string, and a
  substitution that is declared but never referenced in a step is rejected
  outright.
- **`--allow-unauthenticated` is not sufficient by itself.** Cloud Build's
  service account can deploy a revision without permission to set the IAM
  policy; the build reports SUCCESS while every request gets a 403 from the
  Google frontend. Bind `run.invoker` once, separately.
- **Run `arch check` after the formatter, never before.** Running `ruff format`
  expanded a function past the 50-line cap and broke CI on a branch that touched
  no source.
- **A runbook nobody has executed is a hypothesis.** `infra/README.md`
  documented a deploy command that had never been run, and it was wrong. Testing
  the fresh-clone criterion by running the README verbatim is what caught it.

## Commands worth having

```bash
# gate, in the order CI runs it
pytest -n auto --dist=worksteal -q && ruff check . && ruff format --check . \
  && bpsai-pair arch check --strict

# the demo
python scripts/demo.py              # scripted stub, no network
python scripts/demo.py --live       # real Gemini, needs the GCP env

# live Gemini env (note global, not us-central1)
export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.deadman-creds/vertex-sa.json
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=deadman-20260810
export GOOGLE_CLOUD_LOCATION=global

# deploy, always from a clean clone of origin/main, tagged with the SHA
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_TAG=$(git rev-parse HEAD) .
```

## Prompt for the next session

```
Continue work on deadman (~/projects/deadman), my silent-failure monitor for
the All Things Agentic hackathon, deadline Aug 31 5pm PDT.

Read .paircoder/context/state.md and docs/HANDOFF.md first. Both are current.

State: DM1 complete, 12/12, 236 tests, merged. Live and public at
https://deadman-mrapac5nda-uc.a.run.app, GCP project deadman-20260810, image
tagged with the commit SHA.

Next is DM2, "make it real": docs/SPRINT-BRIEF-DM2.md on branch
docs/dm2-sprint-brief. Nine tasks, 275 Cx. Read it, then run /draft-backlog
on it and engage without cutting scope.

The point of DM2: DM1 built a monitor that has never monitored anything.
Nothing runs on a cadence, nothing survives a cold start, no surface watches
real infrastructure. Real world proof matters more to me than a sufficient
contest submission.

Carried over, unresolved:

1. My morning brief has been dead since Aug 4. com.cognify.morning-brief is
   loaded, fires at 6am, and morning_brief_send.py hangs past its 2700s
   deadline and is killed, exit 124. deadman's probe found it. The hang is an
   ops repo bug nobody has diagnosed.

2. The ops repo has 82 changed paths staged and uncommitted, including the
   bpsai-pair payload upgrade. Ask me whether to preserve it on a branch
   before doing anything that could touch that tree.

3. Nobody has verified the actual contest rules. Everything treated as a
   platform requirement traces back to a brief Claude wrote itself. Pull the
   real judging criteria before optimizing for them.

4. Repo fivedollarfridays/deadman is still PRIVATE and must be public before
   judging. The $25 GCP budget alert is unset. The Vertex service account key
   at ~/.deadman-creds/vertex-sa.json on the rig should be deleted after the
   contest.
```
