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
only because that is a sane default for a monitor with a 30-hour staleness
window (`DEFAULT_WINDOW_HOURS` in `src/deadman/self_check.py`), not because
the two schedulers need to agree — see "Two independent clocks" below for why
they deliberately do not.

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

Then read the row back through the store — not through the job, and not
through `GET /`, which does not surface this surface:

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
reported it. Two clocks means one dying is visible on the other's evidence —
the collector going silent shows up as a stale `collector:*` surface
(`src/deadman/verify/collector_liveness.py`); the scheduled self-check going
silent shows up as `self:sweep` reading `STALE` or `NO_EVIDENCE`
(`deadman.self_check.self_check`) — and neither report depends on the clock
that produced the other one.

## What this document does not close

Every command above is written to be run against the live
`deadman-20260810` project by whoever holds `gcloud` credentials for it —
the environment this task was implemented in has no `gcloud` CLI and no
Application Default Credentials configured (`gcloud`: command not found;
`~/.config/gcloud` does not exist), so steps 1–3 above are documented and
reproducible but **not yet executed**. This is the same class of gap
`docs/alerting.md` recorded for DM2.7's SMTP verification rather than
faking: the code, the auth, the store-backed self-check, and every test that
can run without live GCP state are done and green (see
`tests/test_scheduled_auth.py`, `tests/test_self_check_store.py`,
`tests/test_service_schedule.py`, `tests/test_scheduled_startup.py`).
Running steps 1–3 against the real project, from a machine with `gcloud`
authenticated for `deadman-20260810`, is what turns this from a reproducible
runbook into a verified one.
