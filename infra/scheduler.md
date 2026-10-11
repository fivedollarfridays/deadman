# Cloud Scheduler: the cadence nothing in DM1 had

Nothing in DM1 ran on its own. `GET /` answers when a human or a browser
asks; the self-check DM1.11 built only ever proved that *some* instance had
swept *at some point before this request*, and that claim died on every cold
start because it lived in `/tmp` on a container Cloud Run can recycle at any
time. This document is what closes both gaps: a real cron external to the
service, and an authenticated endpoint (`POST /self-check`, see
`src/deadman/scheduled/`) whose own liveness survives the instance that wrote
it.

**This is privileged, billable, live infrastructure.** Every command below
is written to be run once, by hand, by whoever holds `gcloud` credentials for
`deadman-20260810` — the same discipline `infra/README.md` already applies to
the Cloud Run deploy itself, and the same reason: a runbook nobody has
executed is a hypothesis, not a fact, and this project does not get to treat
its own infrastructure claims that way.

## Why the scheduled endpoint is not the public board

`GET /` costs one local sweep and answers with what the instance already
knows. `POST /self-check` costs the same sweep **on demand**, from anyone who
can reach the URL — so unlike the board, it must never be reachable
unauthenticated. It is a separate path, with its own bearer-token secret
(`DEADMAN_SCHEDULER_SECRET`, `src/deadman/scheduled/auth.py`), checked before
a single probe runs. The service refuses to start at all without that secret
set, exactly as it already refuses to start without `DEADMAN_INGEST_SECRET` —
see `tests/test_scheduled_startup.py`.

## Prerequisites

- The Cloud Run service is already deployed (`infra/README.md`) and its URL
  is known:

  ```bash
  URL="$(gcloud run services describe deadman --region=us-central1 --format='value(status.url)')"
  ```

- Enable the Cloud Scheduler API on the project:

  ```bash
  gcloud config set project deadman-20260810
  gcloud services enable cloudscheduler.googleapis.com
  ```

## 1. Generate and set the scheduler secret

Same shape as the ingest secret in `infra/README.md` — generated locally,
set on the service out of band, never committed:

```bash
SCHEDULER_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

gcloud run services update deadman --region=us-central1 \
  --update-env-vars="DEADMAN_SCHEDULER_SECRET=$SCHEDULER_SECRET"
```

For anything beyond a demo, hold it in Secret Manager instead, matching
`infra/README.md`'s ingest-secret guidance:

```bash
printf %s "$SCHEDULER_SECRET" | gcloud secrets create deadman-scheduler-secret --data-file=-
gcloud run services update deadman --region=us-central1 \
  --update-secrets="DEADMAN_SCHEDULER_SECRET=deadman-scheduler-secret:latest"
```

**Redeploying without this variable set takes the service down entirely** —
`deadman.service` reads `DEADMAN_SCHEDULER_SECRET` at import, the same
startup-refusal doctrine `DEADMAN_INGEST_SECRET` already uses (see the
module docstring in `src/deadman/service.py`). Set it *before* the next
`gcloud builds submit`, or the deploy will build and push successfully and
then the revision will fail to serve — a green build hiding a dead service,
which is exactly the failure class `infra/README.md`'s IAM-binding warning
describes for a different variable.

## 2. Create the Cloud Scheduler job

```bash
gcloud scheduler jobs create http deadman-self-check \
  --location=us-central1 \
  --schedule="*/15 * * * *" \
  --uri="${URL}/self-check" \
  --http-method=POST \
  --headers="Authorization=Bearer ${SCHEDULER_SECRET}" \
  --attempt-deadline=30s
```

`*/15 * * * *` — every 15 minutes — matches the collector's own `launchd`
cadence (`infra/launchd/com.deadman.collector.plist`'s `StartInterval=900`)
by choice, not because the two schedulers need to agree — see "Two
independent clocks" below for why they deliberately do not. The service
declares this cadence as `SCHEDULER_INTERVAL_SECONDS` and judges the
self-check stale after three intervals (`WINDOW_SECONDS`, 45 minutes), both in
`src/deadman/scheduled/freshness.py`. **Change the schedule here and that
constant together.** (The window used to be the daily CLI's 30 hours, which
read a scheduler dead for a day as live.)

## 3. Verify the job actually fires

**A job's own status is not evidence.** Cloud Scheduler reporting a job as
`ENABLED` with a healthy `lastAttemptTime` says the HTTP call was made and
got a response; it says nothing about whether the service actually recorded
anything, and a service returning `200` from a code path that silently
skipped the store write would look identical from the scheduler's side. The
proof has to come from the same store the service itself reads.

Trigger one run by hand rather than waiting for the cadence:

```bash
gcloud scheduler jobs run deadman-self-check --location=us-central1
```

Then read the row back through the store, not through the job. (`GET /`
also shows it now, as the `self_check` field; see "Who watches the
scheduler" below. The store read is the one that proves the write landed.)

```bash
python3 -c "
from deadman.store.firestore import FirestoreEvidenceStore
from deadman.self_check import SELF_CHECK_SURFACE

store = FirestoreEvidenceStore(project='deadman-20260810')
row = store.latest(SELF_CHECK_SURFACE)
print(row.observation.value, row.read_at.isoformat(), row.detail)
"
```

A row with `read_at` inside the last few minutes and `detail` carrying
`sweep_size`/`blind` counts is the evidence: the scheduler fired, the
request reached the authenticated endpoint, the endpoint swept, and the
write landed in Firestore where a *different* instance could read it back —
which is the cold-start claim `tests/test_service_schedule.py`'s
`TestSelfEvidenceSurvivesACleanReadFromAnotherInstance` proves in-process
and this step proves against the real deploy.

**Requires `google-cloud-firestore` installed and real `gcloud`
credentials** (`pip install .[firestore]` from a checkout, then
`gcloud auth application-default login` if ADC is not already configured) —
the same one-time setup `infra/README.md`'s Firestore section already
describes for the ingest path.

## Two independent clocks, on purpose

The collector's `launchd` timer (`infra/launchd/com.deadman.collector.plist`)
and this Cloud Scheduler job are two unrelated schedulers on two unrelated
systems: one is a macOS `LaunchAgent` firing on the collector's own machine,
sweeping surfaces Cloud Run cannot reach; the other is a GCP-managed cron
firing an HTTP request at the deployed service, sweeping surfaces the service
*can* reach on its own. Neither depends on the other running, being
reachable, or even existing.

That is deliberate, not incidental. If the two were merged into one
scheduler — say, the collector's `launchd` job also curling
`/self-check` — a single failure (the Mac asleep, `launchd` unloaded, the
collector's process crashed) would silence *both* the collector's delivery
and deadman's own liveness proof at once, which is precisely the
self-concealing failure this whole project exists to catch: the same clock
dying takes down the thing being monitored and the alarm that would have
reported it. The collector going silent shows up as a stale `collector:*`
surface (`src/deadman/verify/collector_liveness.py`), judged and alarmed by
the scheduled sweep, so the Mac's clock is watched from GCP's.

The reverse is **not** true inside this service, and this document used to
claim it was. Every alarm runs inside `POST /self-check`, which only this
Cloud Scheduler job calls; if the job stops, is paused, or its bearer secret
breaks, the code that would notice is the code that stopped running. Nothing
in the service can alarm on its own scheduler. That is what the next section
is for.

## Who watches the scheduler

An independent reader, on a clock this service does not own. The board
publishes the scheduled self-check's age as an additive `self_check` object on
`GET /` (no existing field changed), built by
`src/deadman/scheduled/freshness.py` from the newest `self:sweep` row in the
store:

```json
"self_check": {
  "surface": "self:sweep",
  "liveness": "live",
  "last_run_at": "2026-09-27T18:45:02.114000+00:00",
  "age_seconds": 412.7,
  "window_seconds": 2700,
  "interval_seconds": 900
}
```

**The contract a watcher relies on:** the key is always present on the JSON
board; `liveness` is `live` only when a scheduled sweep completed within
`window_seconds` (three scheduler intervals); `stale` means the last one is
older than that; `no_evidence` means none was ever recorded or the store
could not be read, and `last_run_at` and `age_seconds` are then `null`. A
watcher must treat a missing key, a `null` age, or any `liveness` other than
`live` as the alarm path being dead, not as "nothing to report".
`tests/test_board_self_check_age.py` pins this shape through `GET /`.

The watcher that reads it is the ops repository's board watcher, run every 15
minutes by the Mac's scheduler and judged by the ops freshness monitor on its
own alarm path, which shares neither Cloud Scheduler nor this service's SMTP
rail. Until that watcher gates on `self_check.liveness`, a stopped scheduler is
visible on the board but alarms nowhere.

## Executed, and how that is known

Steps 1–3 were run against the live `deadman-20260810` project during DM2.6,
from a machine with `gcloud` authenticated for it. The job
`deadman-self-check` exists in `us-central1` on `*/15 * * * *`, it attempted
at `2026-08-12T04:40:16Z`, and the row read back out of Firestore — not out
of the job's own status — was:

```
observation healthy · method local_artifact · read_at 2026-08-12T04:40:16Z
summary "scheduled self-check: sweep completed (2 surfaces, 1 blind)"
detail keys: blind, sweep_size
```

That is the cold-start claim proved against the real deploy: the scheduler
fired, the request reached the authenticated endpoint, the endpoint swept, and
the write landed where a different instance can read it back.

A second, cheaper check anyone can run without `gcloud` or Firestore
credentials, because it asks the deployed service rather than the scheduler:

```bash
curl -sS https://deadman-mrapac5nda-uc.a.run.app/ \
  | python3 -c "import json,sys; b=json.load(sys.stdin); print(b['self_check']['liveness'], b['undeclared_surfaces'])"
# live []
```

`self_check.liveness` is `live` when the newest `self:sweep` row in the store
is inside three scheduler intervals, so that word is the store confirming the
scheduler fired and the write landed.

`undeclared_surfaces` is built from `store.latest_per_surface()` (see
`src/deadman/verify/collector_liveness.py`): every surface the store holds
evidence for that no collector declares. Its expected value is `[]`. The
service's own `self:sweep` is not listed there (`SERVICE_OWNED_SURFACES`); it
used to be, which read as a configuration gap for a surface the service
writes itself and already judges in `self_check`. Anything that does appear
is one of two things: evidence arriving for a surface nobody declared, or the
alarm recording its own failure on `alert:email` or `alert:send-record` (see
`docs/alerting.md`).

### One time: remove the leftover `smoke:deploy-check` row

Before DM4 this check printed `['self:sweep', 'smoke:deploy-check']`.
`smoke:deploy-check` is a single row posted by hand during the 2026-08-11 end
to end proof and left in Firestore on purpose at the time. Nothing in this
repository writes it: no script, no Cloud Build step, no CI job and no
collector declaration names that surface, so it will not come back after it
is removed. Until it is removed, `undeclared_surfaces` reads
`['smoke:deploy-check']`.

Run once, from a machine with `google-cloud-firestore` installed and `gcloud`
credentials for the project (the same setup as step 3):

```bash
python3 -c "
from google.cloud import firestore
from deadman.store.firestore import COLLECTION, ROWS, surface_key

client = firestore.Client(project='deadman-20260810')
doc = client.collection(COLLECTION).document(surface_key('smoke:deploy-check'))
rows = list(doc.collection(ROWS).stream())
for row in rows:
    row.reference.delete()
doc.delete()
print('deleted', len(rows), 'row(s) and', doc.path)
"
```

The rows are deleted before their parent because deleting a Firestore
document does not delete its subcollections. The document id is the surface
id percent encoded once, `smoke%3Adeploy-check`, and `surface_key` computes
it, so the snippet never spells it. If you address the document by URL
instead (the REST API or the console), the `%` in that id must itself be
encoded, which makes the path segment `smoke%253Adeploy-check`; the single
encoded form in a URL addresses a document called `smoke:deploy-check`, which
does not exist, and the delete reports success having removed nothing.

Then run the `curl` above again and read `[]`.

This section previously said steps 1–3 were documented but not executed. That
was true when it was written and stopped being true in DM2.6; a runbook whose
status is stale is the same instrument problem as a stale probe.
