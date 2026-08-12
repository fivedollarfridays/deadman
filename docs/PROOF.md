# PROOF — the outage that could not report its own death

This is the case study, and it is about a real failure in a real estate, not a
scenario built to be caught.

Everything below is read out of two committed captures. Nothing here is
recalled:

| file | what it is |
|---|---|
| [`tests/fixtures/real-morning-brief-fault.json`](../tests/fixtures/real-morning-brief-fault.json) | `MorningBriefProbe` run directly against `~/ops/data/brief-send-log.jsonl` on the Mac, the first time anything looked |
| [`tests/fixtures/real-board-capture.json`](../tests/fixtures/real-board-capture.json) | `GET /` against the deployed Cloud Run service, unedited, once the collector was shipping |

`tests/test_proof_doc.py` asserts that every duration and every timestamp in
this document appears in one of those two files. If a capture is ever
refreshed and this prose is not, the suite fails rather than the story
quietly surviving its own evidence.

## The failure

Kevin's `ops` repo sends a morning brief every day. It is the daily status
mail for the estate: what ran, what did not, what needs attention. On
2026-08-04 it stopped sending. It did not crash, did not page anyone, and did
not appear in any error report — `morning_brief_send.py` hangs and is killed
by its own deadline guard, so every morning the job started, ran, wrote
nothing, and ended (`docs/surfaces.md`).

Seven days later it was still not sending, and the only reason anyone found
out is that a probe built for a different purpose was pointed at the log to
see whether the probe worked.

## The evidence

`MorningBriefProbe` against the real log, captured
2026-08-11T20:39:27.797652+00:00:

```json
{
  "surface": "cron:morning-brief",
  "observation": "fault",
  "method": "local_artifact",
  "summary": "no brief sent in 176.7h (window 30h, ~7 missed)",
  "source": "/Users/kevinmasterson/ops/data/brief-send-log.jsonl",
  "detail": {
    "last_send_at": "2026-08-04T11:56:45.586032+00:00",
    "age_hours": 176.71,
    "window_hours": 30.0,
    "row_count": 1
  }
}
```

Three things in that row are worth reading closely.

**`local_artifact`, not `reported`.** The probe read the send log itself. It
did not ask the scheduler whether the job ran, and it did not read the file's
mtime — the timestamp comes from *inside* the newest row, because a checkout
or an rsync rewrites mtime and turns a freshness check green with nothing
having run.

**`row_count: 1`.** The log holds exactly one row. There is no history to
average, no trend to fit, and nothing that looks like a metric. This is the
kind of evidence real estates actually have.

**`176.7h` against a `30h` window.** The window is 24h of cadence plus 6h of
slack, so a brief that runs late is not an incident. Seven consecutive missed
days is not late.

## The timeline

| when | what happened | how we know |
|---|---|---|
| 2026-08-04T11:56:45.586032+00:00 | the last brief anyone received; the last row the log ever got | `last_send_at`, both captures |
| every morning after | the job ran, hung, was killed by its deadline guard, appended nothing | `docs/surfaces.md`; the log stayed at `row_count: 1` |
| 2026-08-11T20:39:27.797652+00:00 | first observation: `FAULT`, 176.7h stale, found by accident while testing a probe | `real-morning-brief-fault.json` |
| 2026-08-12T05:39:55.070216+00:00 | the `kevin-mac` collector's sweep reads it and ships it to Cloud Run | `real-board-capture.json` |
| 2026-08-12T05:42:43+00:00 | the public board carries it: `FAULT`, 185.7h | `real-board-capture.json` |

The gap between the second row and the third is the entire point of this
project. Between them, nothing changed about the world. The brief was exactly
as dead on 2026-08-05 as it was on 2026-08-11. The only thing that changed is
that somebody looked.

## Why nobody looked: the outage was self-concealing

The morning brief *is* the alerting channel for this estate. It is the thing
that reports on everything else, and where a failure would have been
announced.

So a failure *of* the brief has no announcer. There is no alert to ignore and
no red dashboard to walk past — the daily mail simply stops arriving, and an
absent email looks exactly like a quiet week. Every conventional signal was
green:

- the launchd job was loaded and scheduled;
- it ran daily and exited without an error anyone saw;
- the log file existed, was readable, and its mtime kept moving;
- no threshold was crossed, because nothing about this failure is a number.

That is what self-concealing means here, and it is the reason this repository
exists. A monitor that trusts a heartbeat would have reported this surface
healthy for seven days, which is worse than having no monitor at all: it
would have been actively answering the question, wrongly.

**Which is why the alarm may not travel over a monitored rail.**
`deadman.remediate.alert.AlertChannel` refuses at construction — not at send
time — to sit on any surface deadman watches. Configuring the alarm on the
morning brief raises immediately. That rule is this outage written down.

## What the board says now

`GET https://deadman-mrapac5nda-uc.a.run.app/`, captured
2026-08-12T05:42:43+00:00. Two rows, both about the same surface:

```json
{
  "surface": "cron:morning-brief",
  "observation": "fault",
  "method": "reported",
  "summary": "no brief sent in 185.7h (window 30h, ~7 missed)",
  "source": "brief-send-log.jsonl",
  "read_at": "2026-08-12T05:39:55.070216+00:00",
  "detail": {
    "window_hours": 30.0,
    "last_send_at": "2026-08-04T11:56:45.586032+00:00",
    "row_count": 1,
    "age_hours": 185.72,
    "withheld": ["collector_id", "received_at", "reported_method", "wire_row_id"]
  }
}
```

```json
{
  "surface": "cron:morning-brief",
  "observation": "unobservable",
  "method": "reported",
  "summary": "cannot observe cron:morning-brief: log directory does not exist (path misconfigured?)",
  "source": "morning-brief.jsonl",
  "detail": {"reason": "log directory does not exist (path misconfigured?)", "withheld": ["path"]}
}
```

The same surface, twice, with two different verdicts, and both are correct.
The first row is the Mac's collector reporting what it read on the machine
where the log lives. The second is the Cloud Run instance answering honestly
that it cannot see any such log — Cloud Run has no `~/ops` — which is
`UNOBSERVABLE`, listed under `blind_spots`, and never counted as healthy.

**`method` is `reported` on the collector's row, not `local_artifact`.** The
collector read a file; the service received a *report* that a file was read.
`deadman.ingest.arrival` caps every arriving row at the weakest tier on the
ladder and preserves the collector's claim in `detail.reported_method` rather
than erasing it. That downgrade is expensive on purpose: every action floor in
`remediate/registry.py` sits above what a `reported` citation can carry, so a
diagnosis resting only on relayed evidence escalates to a human instead of
moving infrastructure.

Alongside those two rows the same board carries `collector:kevin-mac` as
`healthy`, "last reported 168s ago, inside its declared 1800s deadline". That
row is why the FAULT above can be believed: an empty inbox and a healthy
estate look identical on a wire, so the collector's own silence is watched
separately.

The capture came from the deployed revision (image tag `86c3662`), which
predates DM2C.1 — so no row in it carries `reported_by` or `held_since`. Those
fields are in the code and in `sample-outputs/board.json`; they are not in this
capture, and this document does not pretend otherwise.

## The detection latency, as arithmetic

Every term below is a committed number, not an estimate.

| term | value | source |
|---|---|---|
| the probe's tolerance before a miss is a fault | `30h` | `MorningBriefProbe.DEFAULT_WINDOW_HOURS`, `window_hours` in both captures |
| the collector's sweep cadence | `900s` | `cadence_seconds` in the board capture; `infra/launchd/com.deadman.collector.plist` |
| how long the collector may be silent before its surfaces stop reading healthy | `1800s` | `silent_after_seconds` in the board capture |

A brief that fails to send becomes a fault 30h later by design, and the next
sweep is at most 900s after that. **Worst case, the outage is on the public
board a little over 30 hours after the first missed send** — nearly all of
which is the deliberate tolerance for a late brief, not detection lag.

Against that: **176.7h** at the first observation, still climbing to **185.7h**
a day later. Seven days, found by accident, and it would still be undetected
if nobody had gone looking.

The 1800s deadline is the term that makes the rest mean anything. If the
collector dies, the morning brief surface does not keep reading healthy off
its last report — after 1800s of silence it reads `UNOBSERVABLE`, because what
was last heard is not news about now. A latency claim that assumes the
reporter is alive is the heartbeat problem one level up.

## What a threshold monitor would have said

The same estate, the same moment, counted the way conventional monitoring
counts: the disk is fine, the collector is running, the process is up, no
number crossed a line. Green.

The captured board does not agree. Of five rows it counts three healthy, one
fault and one blind — and it publishes `blind_spots` as its own field
precisely so the blind one cannot be quietly rounded into the healthy pile.
Counting an unobservable surface as healthy is not a rounding error; it is the
same false green that let this outage run for a week.

## What this does not prove

- **The fault has not been fixed by deadman.** No shipped action repairs a
  hung cron job on a laptop, so the cause classifies `UNKNOWN` and the correct
  automated outcome is an escalation to a human. The demo runs exactly that
  path against this surface (`scripts/demo_real_surface.py`).
- **One outage is not a base rate.** This is a single real failure detected by
  a probe written before it was found, not a measured false-positive rate over
  time.
- **The capture is a moment, not a monitor.** These two files record what was
  true when they were taken. The live board may since have healed — the ops
  fix shipped on 2026-08-11 — and if it has, that changes nothing about what
  the captures show.
