# The demo — run sheet

One take, start to finish, nothing edited. This is the sheet for the topology
that exists today: a collector on the Mac sweeping every 900s, the service on
Cloud Run holding what it reports, Cloud Scheduler firing the self-check, and
an alarm that has actually reached an inbox.

The case study behind it is [`docs/PROOF.md`](PROOF.md). Read that first; this
sheet is how it gets shown.

## Two rules the recording has to obey

**1. Unedited, single take.** No cuts, no re-rolls, no splicing a better
Gemini response in later. If something goes wrong, narrate it and keep going —
see "when it does not heal" below, which is the one outcome most worth having
on camera anyway.

**2. Google Cloud has to be visible, not asserted.** Saying "it runs on Cloud
Run" is not proof of it. The take must show, on screen: the deployed service
answering on its `run.app` URL, and the Cloud Console with the service and the
Cloud Scheduler job in it. Beats 1 and 4 below are where that happens.

*Provenance, since this project does not get to assert things either:* the
judging weights are verified from the real Devpost page and recorded in
`plans/backlogs/DM2C-close.md` — Innovation & Operational Utility 40%,
Architectural Discipline 30%, Demo & Production Readiness 30%. The two rules
above are the submission requirements this sheet is built around and are
recorded in `docs/SPRINT-BRIEF-DM1.md`. **Re-read the rules page immediately
before recording** and change this sheet if either has moved; a run sheet
citing rules nobody re-checked is the same failure mode as a heartbeat.

## Before the camera rolls

Everything here is pre-flight, not part of the take. A take spent waiting for
a collector's next sweep is a take wasted.

```bash
# 1. The service is up, and it is serving the commit you think it is.
curl -sS https://deadman-mrapac5nda-uc.a.run.app/ | python3 -m json.tool | head -30
gcloud run services describe deadman --region=us-central1 \
  --format='value(spec.template.spec.containers[0].image)'   # tag == commit SHA

# 2. The collector is loaded, on cadence, and exiting clean.
launchctl print gui/$(id -u)/com.deadman.collector | grep -E 'interval|last exit'
#   "state = not running" between sweeps is correct: it is a 900s timer, not a daemon.

# 3. It has actually reported recently, asked of the service rather than of itself.
curl -sS https://deadman-mrapac5nda-uc.a.run.app/ | python3 -c \
  "import json,sys; print([r['summary'] for r in json.load(sys.stdin)['surfaces'] \
   if r['surface'].startswith('collector:')])"
ls "$(python3 -c "import json;print(json.load(open('$HOME/.deadman/collector.json'))['spool_dir'])")" \
  2>/dev/null | wc -l    # 0 = nothing stuck undelivered

# 4. Live Gemini works from this machine, right now.
pip install -e '.[gemini]' -c constraints.txt
export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.deadman-creds/vertex-sa.json
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=deadman-20260810
export GOOGLE_CLOUD_LOCATION=global      # note: global, not us-central1
python scripts/gemini_smoke.py

# 5. Rehearse the whole sequence once, without spending a call.
python scripts/demo.py
```

Have open, before recording: a browser tab on the service URL, a Cloud Console
tab on Cloud Run and Cloud Scheduler, the inbox holding the alarm mail, and one
terminal.

## The take

**1 · The board, live. (~35s)** Load
`https://deadman-mrapac5nda-uc.a.run.app/` in the browser. This is the Google
Cloud requirement being satisfied visibly, and it is also the strongest thing
in the demo, so it goes first.

Read three things off it out loud:

- `cron:morning-brief` is `fault` — a real outage in a real estate, not a
  fixture. On the capture in `tests/fixtures/real-board-capture.json` it reads
  "no brief sent in 185.7h (window 30h, ~7 missed)".
- the same surface appears a second time as `unobservable`, because Cloud Run
  cannot see a log on a Mac, and it is listed under `blind_spots` rather than
  counted healthy.
- `collector:kevin-mac` is `healthy`, "inside its declared 1800s deadline" —
  which is what makes the fault above worth believing.

If the live board has healed since (the ops fix shipped 2026-08-11), say so on
camera and show the committed capture instead. A case study that survives its
own subject recovering is the stronger version.

**2 · Where that came from: the collector on the Mac. (~30s)** Terminal:

```bash
launchctl print gui/$(id -u)/com.deadman.collector | grep -E 'interval|last exit'
source ~/.deadman/collector-env.sh          # the shared secret, never in the plist
deadman-collector --config ~/.deadman/collector.json --dry-run
```

The dry run prints the batch it *would* send and calls the transport zero
times. Point at `run interval = 900 seconds` — that number is one term of the
detection latency claim, and the larger one is the probe's own 30h tolerance.

**3 · What crossing the wire costs. (~20s)** The dry-run batch you just printed
says `"method": "local_artifact"` on the morning-brief row. The same row on the
board says `"method": "reported"`. Put the two side by side: the collector read
a file; the service received a report that a file was read, and records the
weaker claim rather than inheriting the stronger one.

Every action floor sits above what `reported` can carry, so relayed evidence
escalates to a human instead of moving infrastructure. This is the one design
decision most worth 20 seconds.

**4 · The watcher is itself watched, on a second clock. (~25s)** Cloud Console
on the Cloud Scheduler job `deadman-self-check`, `*/15 * * * *`. Then back to
the board: `undeclared_surfaces` contains `self:sweep`, which is the service's
own liveness row sitting in Firestore — written by a scheduled sweep, read back
by a different instance, surviving the cold start that killed the DM1 version.

Say why there are two clocks: launchd on the Mac and Cloud Scheduler in GCP,
deliberately unrelated, so one dying is visible in the other's evidence.

**5 · The alarm. (~15s)** Show the delivered mail in the inbox. It went out
over email — a rail deadman does not watch — and `AlertChannel` refuses at
*construction* to sit on a monitored surface. That rule is the outage in
`PROOF.md` written down: the morning brief was both the thing that died and the
channel that would have announced it.

**6 · Break it and heal it, live. (~90s)**

```bash
python scripts/demo.py --live
```

Nine stages. Two things to narrate:

- **Stage 1 has nothing standing in.** A real `MorningBriefProbe` over a real
  file: the break is the outage's own last log row, read out of the committed
  capture; detection is computed off the real clock; the cause classifies
  `unknown`, so it escalates to a human rather than guessing an action — there
  is no shipped fix for a hung cron job on a laptop, and inventing one is the
  thing this design refuses. The heal is the write a repaired brief job makes,
  and what proves it is the *next observation*, not the write.
- **Stages 2–9 use the one stub, and you say so out loud.** The phone relay is
  simulated. A carrier outage cannot be arranged on demand, so the one thing
  that cannot be broken on command is the one thing injected, through the same
  `RelayClient` seam the probe already exposes for tests; the 503 it reports is
  a shape that rail genuinely produces. It stays in the demo because it is the
  surface that carries the *automated* act-and-verify path end to end.

A demo that hides its stub is doing the thing this project exists to argue
against.

**7 · Close on the arithmetic. (~15s)** 30h of deliberate tolerance plus one
900s sweep, against 176.7h that went unnoticed and was found by accident.
Not "we would have caught it faster" — the numbers are in `docs/PROOF.md` and
every one of them is read out of a committed capture by a test.

## What is real and what is not

Real: the probes, the evidence model, the collector and its spool, the signed
ingest, the arrival downgrade, the Firestore store, the Gemini call through the
ADK, the grounding rules, cause classification, action selection, the executor,
the verification loop, the self-check, the alert channel, the deployed service,
the scheduler job. All shipped code, none of it special-cased for the demo.

Simulated: **the phone relay only**, and it is named on camera.

## When it does not heal

Across four live rehearsals of the relay act on 2026-08-11:

| run | diagnosis | confidence | verification | wall |
|---|---|---|---|---|
| 1 | grounded | 0.85 | verified | 4.6s |
| 2 | grounded | 0.85 | verified | 7.8s |
| 3 | grounded | 0.85 | verified | 7.0s |
| 4 | **ungrounded** | 0.0 | not attempted | 10.5s |

On run 4, Gemini returned a hypothesis that read correctly and cited nothing.
Grounding threw it out, and because nothing was grounded, nothing was allowed
to select an action. The demo prints that as a completion, not a failure.

**Do not re-roll it if it happens on camera.** Narrate it. An agent that
refuses to act on its own model's uncited assertion is the entire argument, and
no scripted success demonstrates it half as well.

Two caveats on that table. It measured the relay act *before* stage 1 existed,
and stage 1 makes a second live model call — so re-measure during rehearsal and
expect roughly double the model latency. And the one-in-four figure is four
runs, not a rate: it is the honest sample size, stated as such.

## What rehearsal caught

The ungrounded outcome used to crash. `verify_remediation` raised `ValueError`
when the diagnosis cited nothing, because its guard could not distinguish "the
caller passed an unrelated probe", a programmer error worth being loud about,
from "every citation was rejected", which is ordinary reality on a
non-deterministic model.

A monitor that dies whenever its model has an off moment has become the outage
it was watching for. It now returns `NOT_ATTEMPTED`. See
`tests/test_remediate_verify_ungrounded.py`.

That defect was reachable only by running the thing live, more than once. It is
the argument for the rehearsal requirement in one bug.

It came back once, one layer up. On 2026-09-25 the live take crashed at stage 1
with an `IndexError` on the alarm line: the stage-1 model call came back
uncited, the loop correctly reported `NOT_ATTEMPTED` with no attempts, and the
real-surface segment only raised its alarm *per attempt*, so a real FAULT
produced no alarm at all. A fault with no alarm is the failure this project
exists to catch. The segment now alarms on the FAULT itself, whatever the model
said, which is what the shipped `scheduled/alerting.py` path has always done;
the alarm carries the executor's reason, including "diagnosis is ungrounded".
If an alarm is ever missing, stage 1 prints `NO ALARM` and fails the run
rather than crashing. See `tests/test_demo_stage1_ungrounded.py`.

## Rehearsing without spending a call

```bash
python scripts/demo.py            # scripted stub, no network, deterministic
```

The stub reads the evidence ids back out of the prompt and returns a
correctly-shaped response. It is not a model and does not pretend to be one; it
exists because the demo mints a fresh canary token every run, so no static
recording can ever cite ids that resolve. Use it to rehearse the sequence and
to prove the pipeline. Use `--live` for the take.

## If the take goes wrong

- **Gemini returns ungrounded** — narrate it, do not re-roll. See above.
- **The live board has healed** — say so, show the committed capture, and make
  the point that the case study was deliberately written from captures for
  exactly this reason.
- **The collector has not reported recently** — the board will say so itself,
  as a stale surface rather than a healthy one. That is also a demo of the
  liveness rule; take the win and explain it.
- **A live call fails outright** — fall back to `python scripts/demo.py` and
  say plainly that the model call is unavailable and this is the replayed path.
  Never present the stub as the live model.
