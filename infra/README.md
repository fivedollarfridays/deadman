# Deploying deadman to Cloud Run

The `deadman` service is a zero-dependency Python WSGI app (`src/deadman/service.py`)
that publishes the current board — the latest evidence from every probe that
needs no secrets to run — as JSON at `GET /`. It is built and deployed through
Cloud Build so no local Docker daemon is required.

## Prerequisites

- A GCP project with billing enabled.
- The `gcloud` CLI, authenticated: `gcloud auth login`.
- These APIs enabled on the project:
  - `cloudbuild.googleapis.com` (Cloud Build)
  - `run.googleapis.com` (Cloud Run)
  - `artifactregistry.googleapis.com` or `containerregistry.googleapis.com`
    (image storage — `cloudbuild.yaml` pushes to `gcr.io/$PROJECT_ID/...`,
    which needs Container Registry or the Artifact Registry GCR shim)

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable cloudbuild.googleapis.com run.googleapis.com \
  artifactregistry.googleapis.com
```

## Deploy

From a clean checkout of the commit you intend to ship:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_TAG=$(git rev-parse HEAD) .
```

This uploads the source to Cloud Build, which builds the image
(`Dockerfile`), pushes it to `gcr.io/$PROJECT_ID/deadman`, and deploys it to
Cloud Run — all on Google's infrastructure, never touching a local Docker
daemon.

**Tag with the commit SHA, and check the tree is clean first.** The tag is the
only link between a running revision and the source that produced it. Deploy
from a dirty tree and the tag names a commit the image does not contain, which
is worse than no tag at all: it is a provenance claim that is confidently
wrong. `git status --porcelain` should be empty.

```bash
gcloud run services describe deadman --region=us-central1 \
  --format='value(spec.template.spec.containers[0].image)'
# -> gcr.io/PROJECT/deadman:ba550b6b681037503418c0c0c54d6da54e9a0dc7
```

That command is the whole point of tagging. Anyone can ask a running service
which commit it is, and get an answer they can `git show`.

The bare form works and is what the fresh-clone check runs, but it tags the
image `latest`, which answers that question with nothing:

```bash
gcloud builds submit --config cloudbuild.yaml .
```

A service whose provenance is unknowable is the failure mode this whole
project is an argument against. Do not let this one be an example of it.

Service name and region are overridable the same way:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_SERVICE=deadman,_REGION=us-central1,_TAG=$(git rev-parse HEAD) .
```

### Why the image reference is spelled out in every step

`cloudbuild.yaml` repeats `gcr.io/$PROJECT_ID/deadman:$_TAG` in each step
rather than assembling it once into an `_IMAGE` substitution. That is
deliberate, and both halves of the reason cost a failed build to learn.

Cloud Build expands substitutions in step args and in `images:`, but **not
inside another substitution's default value.** An `_IMAGE` defaulting to
`gcr.io/${PROJECT_ID}/deadman:latest` reaches the builder as that literal
string and dies on `could not parse reference`. Nesting a `${_TAG}` inside
`_IMAGE` fails differently and earlier: `_TAG` then appears nowhere the
config recognizes as a use, and Cloud Build rejects any substitution that is
declared and never referenced.

`SHORT_SHA` is no help either. It is a built-in that populates only for
trigger-based builds, and built-ins cannot be passed to a manual submit.

## Grant public access

The `--allow-unauthenticated` flag in the deploy step is **not sufficient on
its own.** Cloud Build's default service account can deploy a revision without
necessarily holding permission to set the service's IAM policy, and when it
lacks that permission the deploy still reports SUCCESS while every request
gets a `403 Forbidden` from the Google frontend, before it ever reaches the
container. Green build, unreachable service, no error anywhere connecting the
two. Bind the invoker role once, with your own credentials:

```bash
gcloud run services add-iam-policy-binding deadman \
  --region=us-central1 --member=allUsers --role=roles/run.invoker
```

The binding survives redeploys, so this is one-time per service.

## Find the URL

```bash
gcloud run services describe deadman --region=us-central1 --format='value(status.url)'
```

## Verify

```bash
curl "$(gcloud run services describe deadman --region=us-central1 --format='value(status.url)')/"
```

Returns the current board as JSON, e.g.:

```json
{
  "surfaces": [
    {"surface": "host:disk/", "observation": "healthy", "...": "..."},
    {"surface": "cron:morning-brief", "observation": "unobservable", "...": "..."}
  ],
  "blind_spots": ["cron:morning-brief"],
  "healthy_count": 1,
  "fault_count": 0,
  "blind_count": 1
}
```

`cron:morning-brief` reads `unobservable` on a stock deployment because
`DEADMAN_BRIEF_LOG` has no log to point at yet — an honest blind spot, not a
bug (see `deadman.probes.base` on why absence of evidence is never reported
as health). Point it at a real send log with an env var on the Cloud Run
service to light that surface up:

```bash
gcloud run services update deadman --region=us-central1 \
  --update-env-vars=DEADMAN_BRIEF_LOG=/path/inside/the/container/to/the/log
```

(`--update-env-vars`, never `--set-env-vars` — the latter replaces the whole
environment and wipes `DEADMAN_INGEST_SECRET`; see `cloudbuild.yaml`.)

Once a collector ships the brief surface via `POST /evidence`, the local
probe is pure blind spot: inside the container the log can never exist. Set
the var **empty** to drop the probe from the service's own sweep — an
explicit, visible-in-the-deploy opt-out, deliberately not an automatic
`exists()` check (that would also silence a genuinely misconfigured path):

```bash
gcloud run services update deadman --region=us-central1 \
  --update-env-vars=DEADMAN_BRIEF_LOG=
```

Read `host:disk/` on this deployment with the same suspicion. Inside Cloud
Run it measures the container's own ephemeral filesystem, which starts
effectively empty and reports something close to 100% free on every cold
start. That number is true and useless: the volume this probe was written
about is a workstation's, and no container can see it. The hosted board is a
demonstration surface. Trending a real host means running the probe on that
host and shipping its evidence here — which is what `POST /evidence` below is
for.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Set by Cloud Run automatically; the service reads it. |
| `DEADMAN_INGEST_SECRET` | **none — the service refuses to start** | Shared secret a collector signs its batches with. See "Ingest" below. |
| `DEADMAN_SCHEDULER_SECRET` | **none — the service refuses to start** | Bearer token Cloud Scheduler sends to trigger the scheduled self-check. See `infra/scheduler.md`. |
| `DEADMAN_STORE_BACKEND` | `memory` | `firestore` or `memory`. `cloudbuild.yaml` sets `firestore` on deploy; the `memory` default is for local runs only, and on Cloud Run it would forget the estate on every scale-to-zero. |
| `DEADMAN_FIRESTORE_PROJECT` | the SDK's default | GCP project holding the Firestore database. |
| `DEADMAN_COLLECTORS` | unset — **the service warns on stderr and watches nobody's silence** | Path to the collector liveness declaration (see "Collector liveness" below). A named file that cannot be read or parsed is a startup failure. |
| `DEADMAN_BRIEF_LOG` | `/var/log/deadman/morning-brief.jsonl` | Path the morning-brief probe reads. Set empty to disable the service-side probe (the surface then rides in via ingest only). |
| `DEADMAN_DISK_HISTORY` | `/tmp/deadman/disk-history.jsonl` | Where the disk probe appends its trend samples. Cloud Run's filesystem is ephemeral per instance, so the trend resets on every cold start — acceptable for the demo board; a persistent volume is out of scope for this task. |

## Ingest: `POST /evidence`

The board's own probes can only see the container they run in. Every surface
that matters lives somewhere else, so a collector runs where the surfaces are
and ships signed batches here. `src/deadman/ingest/` is the receiving end.

### The secret is a prerequisite, not an option

**The service will not import without `DEADMAN_INGEST_SECRET`.** That is
deliberate: an unconfigured deploy that started anyway would serve an endpoint
accepting evidence from anyone who can reach the URL, and the board would then
show a monitored estate that was in fact whatever the last caller said it was.
A container that will not boot is loud; a guestbook pretending to be a monitor
is not.

Generate one and set it out of band — never in `cloudbuild.yaml`, which is
committed:

```bash
SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

gcloud run services update deadman --region=us-central1 \
  --update-env-vars="DEADMAN_INGEST_SECRET=$SECRET"
```

For anything beyond a demo, hold it in Secret Manager and mount it instead, so
the value is not readable from the service description:

```bash
printf %s "$SECRET" | gcloud secrets create deadman-ingest-secret --data-file=-
gcloud run services update deadman --region=us-central1 \
  --update-secrets="DEADMAN_INGEST_SECRET=deadman-ingest-secret:latest"
```

Keep the same value on the collector side; it is what
`deadman.ingest.auth.sign` uses, and a mismatch is a `401` on every batch.

The deploy step in `cloudbuild.yaml` uses `--update-env-vars`, not
`--set-env-vars`, so redeploying preserves whichever of these you used.
`--set-env-vars` replaces the entire environment and would take the service
down on the next build.

### Collector liveness: what makes an empty board mean something

Accepting evidence over a wire creates a failure this project cannot tolerate:
a healthy estate and a dead collector deliver the same empty inbox, and the
board reads the inbox. So the service is told, in configuration, which
collectors are expected to report, how often, and about what.

Copy `infra/collector/collectors.example.json`, which declares the same
collectors and surfaces as `collector.example.json` and
`collector-rig.example.json` beside it — one entry per machine:

```json
{
  "collectors": [
    {
      "collector_id": "kevin-mac",
      "interval_seconds": 900,
      "surfaces": ["host:mac/disk", "cron:morning-brief"]
    },
    {
      "collector_id": "kevin-rig",
      "interval_seconds": 900,
      "surfaces": ["host:rig/disk"]
    }
  ]
}
```

`host:mac/disk` and `host:rig/disk` are deliberately distinct ids for the same
kind of probe (`DiskProbe`'s `host` argument, set once per machine's config —
see "Real surfaces" in `docs/surfaces.md`) — a full volume on one machine says
nothing about the other, and a shared id would let one machine's healthy
report paper over the other's fault.

`collector_id` must match what the collector signs its batches with, and
`interval_seconds` must match its `StartInterval` in the launchd plist (900
in both, today). `grace_intervals` defaults to `1.0`, so silence becomes a
fault after the cadence plus one whole missed run — 30 minutes here.

**The cadence is declared, never inferred from what a collector has actually
been doing.** A collector that dies slowly would otherwise teach the monitor
to expect its own lengthening silences, and the board would stay green the
whole way down.

Ship the file with the image (it is configuration, not a secret) and point
the variable at it:

```bash
gcloud run services update deadman --region=us-central1 \
  --update-env-vars="DEADMAN_COLLECTORS=/app/infra/collector/collectors.json"
```

With it set, `GET /` gains a row per collector — `collector:kevin-mac`,
`FAULT` the moment it goes quiet — and the summary separates surfaces that
reported recently (`fresh_count`), reported too long ago (`stale_count`) and
have never reported at all (`unreported_count`). A surface whose newest
reading is older than its cadence reads `UNOBSERVABLE`, never `HEALTHY`:
what we last heard is not news about now.

Leaving the variable unset is legal and logs a warning on every boot, because
the consequence is invisible on the board it produces.

### Firestore has to exist first

`cloudbuild.yaml` sets `DEADMAN_STORE_BACKEND=firestore`, and the Firestore
backend raises at construction rather than degrading, so the database must
exist in the project before the first deploy that carries this setting:

```bash
gcloud services enable firestore.googleapis.com
gcloud firestore databases create --location=nam5
```

The Cloud Run service account also needs `roles/datastore.user`. As with the
invoker binding above, a missing role here produces a startup failure whose
message names permissions rather than configuration.

### What arrives is not what was observed

A collector reads a log on a Mac. What this service then holds is a *report
of* that read, not the read — so ingest caps the method of every arriving row
at `reported`, the weakest tier on `Method`'s trust ladder, and preserves the
collector's claim in `detail.reported_method`. See
`src/deadman/ingest/arrival.py` for why, including what it costs: a diagnosis
resting only on collected evidence escalates to a human instead of moving
infrastructure, because every action floor in the remediation registry sits
above the confidence ceiling a `reported` citation earns.

Each stored row also carries `detail.collector_id`, `detail.received_at` (this
service's clock at delivery, distinct from the collector's `read_at`), and
`detail.wire_row_id` (the observation's identity, which is what makes a
re-sent batch idempotent).

### Posting a batch by hand

Verified end to end against `deadman.ingest.endpoint` — `openssl`'s HMAC and
`deadman.ingest.auth.sign` agree on this exact body:

```bash
URL="$(gcloud run services describe deadman --region=us-central1 --format='value(status.url)')"
BODY='{"collector_id":"laptop","rows":[{"detail":{},"method":"local_artifact","observation":"healthy","read_at":"2026-08-11T07:00:00+00:00","source":"by hand","summary":"a hand-rolled row","surface":"demo:manual"}],"signed_at":"2026-08-11T07:00:00+00:00","version":1}'
SIG="$(printf %s "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $NF}')"

curl -X POST "$URL/evidence" -H "X-Deadman-Signature: $SIG" -d "$BODY"
```

`signed_at` must be within five minutes of the service's clock or the batch is
refused as stale, so edit both timestamps before running this. The signature
covers the **exact bytes**, so any edit to `BODY` after computing `SIG`
invalidates it — which is the point.

Expected replies: `200` with `{"stored": n, "duplicates": m}`; `401` for a
missing, wrong or stale signature; `400` for a body that is not a valid batch;
`413` for a body over 256 KiB. Nothing is stored on any of the failures.

## The collector

The board's own probes can only see the container they run in (see
"Ingest" above). `src/deadman/collector/` is the process that runs on a
real machine, sweeps whatever probes a config file names, signs the result
in the DM2.2 wire format, and posts it here. Nothing about *which* probes
run is compiled into the collector — see `src/deadman/collector/config.py`
and `infra/collector/collector.example.json` — so pointing it at a new
surface on a new machine is a new config file, never a new build.

### Store-and-forward

A batch the collector could not deliver — the service unreachable, a
non-200 reply — is written to `spool_dir` (from the config file) rather than
discarded, and a later run resends it before attempting its own fresh
sweep, oldest first. The spool is a directory on disk, not process state, so
it survives a crash or a reboot with nothing extra to configure. Every
resend is signed fresh, at the moment it is actually sent — see
`src/deadman/collector/run.py`'s module docstring for why reusing the
original signature would make an honest retry look like a stale replay.

### Try it before it ships anything

```bash
deadman-collector --config infra/collector/collector.example.json --dry-run
```

Prints the exact batch a real run would ship — every row from every
configured probe, signed-envelope shape and all — and makes **zero** network
calls. This is the thing to run first on a new machine, before the config
is trusted with a real ingest URL.

### Installing the collector on a Mac

Prerequisites: the package installed somewhere `python3` can import it
(`pip install .` or `pip install -e .` from a clone of this repo), a config
file (copy `infra/collector/collector.example.json` and point its two paths
at real files on this machine), and the same `DEADMAN_INGEST_SECRET` value
the deployed service uses.

The secret is never written into the plist or committed anywhere — it is
sourced from `~/.deadman/collector-env.sh` at run time, the same rule
`tests/test_ingest_startup.py::TestNothingSecretIsCommitted` already
enforces on the service side:

The **directory** permission matters as much as the file's. The plist `source`s
this script as you, so anyone who can create or replace a file in `~/.deadman`
gets code execution in your session — and `mkdir -p` alone leaves the directory
at whatever your umask happens to be:

```bash
mkdir -p ~/.deadman
chmod 700 ~/.deadman
cat > ~/.deadman/collector-env.sh <<'EOF'
export DEADMAN_INGEST_SECRET="the same value the Cloud Run service has"
EOF
chmod 600 ~/.deadman/collector-env.sh
```

Then materialize `infra/launchd/com.deadman.collector.plist` with real paths
and load it. **Validate the generated plist before loading it**: the paths are
interpolated into XML, so a path containing `&`, `<` or `#` produces a file
that is either malformed or silently wrong, and `launchctl` failing later is a
much worse place to find out:

```bash
sed \
  -e "s#__DEADMAN_COLLECTOR_BIN__#$(command -v deadman-collector)#" \
  -e "s#__DEADMAN_COLLECTOR_CONFIG__#$PWD/infra/collector/collector.example.json#" \
  infra/launchd/com.deadman.collector.plist > ~/Library/LaunchAgents/com.deadman.collector.plist \
  && plutil -lint ~/Library/LaunchAgents/com.deadman.collector.plist \
  && launchctl load ~/Library/LaunchAgents/com.deadman.collector.plist
```

`plutil -lint` is the gate: if the substitution corrupted the XML the chain
stops there and nothing is loaded, rather than launchd quietly refusing to run
a job you believe is installed. (`#` is the `sed` delimiter above, so a
repository path containing `#` breaks the substitution itself — if `plutil`
complains, check `$PWD` before anything else.)

launchd now runs the collector every 15 minutes (`StartInterval`, see the
plist's own comment for why not a calendar interval) and once immediately
(`RunAtLoad`). Logs land at `/tmp/deadman/collector.log`. To stop it:

### Installing on a second machine (the rig)

`infra/collector/collector-rig.example.json` is the same steps above with a
different config file: same `disk` probe type, a different `collector_id`
and `host` argument. No new probe code, because `DiskProbe` already answers
"is this volume trending toward the floor" for any volume it is pointed at —
adding a machine is naming it in a config file the way the disk probe
docstring's "adding a surface is a config edit" claim is meant to be read.
The rig has no morning-brief log, so its config carries only the disk probe.

```bash
launchctl unload ~/Library/LaunchAgents/com.deadman.collector.plist
```

## Local verification without GCP

The Dockerfile can be built and run with any local Docker daemon to sanity
check the image before spending a Cloud Build run:

```bash
docker build -t deadman-local .
docker run --rm -p 8080:8080 deadman-local
curl http://localhost:8080/
```

This is optional — `cloudbuild.yaml` never depends on a local daemon being
present or working.
