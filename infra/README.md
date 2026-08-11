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

From the repository root:

```bash
gcloud builds submit --config cloudbuild.yaml .
```

This uploads the source to Cloud Build, which builds the image
(`Dockerfile`), pushes it to `gcr.io/$PROJECT_ID/deadman`, and deploys it to
Cloud Run — all on Google's infrastructure, never touching a local Docker
daemon. Default substitutions deploy a service named `deadman` to
`us-central1`; override either with `--substitutions`:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_SERVICE=deadman,_REGION=us-central1 .
```

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
  --set-env-vars=DEADMAN_BRIEF_LOG=/path/inside/the/container/to/the/log
```

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Set by Cloud Run automatically; the service reads it. |
| `DEADMAN_BRIEF_LOG` | `/var/log/deadman/morning-brief.jsonl` | Path the morning-brief probe reads. |
| `DEADMAN_DISK_HISTORY` | `/tmp/deadman/disk-history.jsonl` | Where the disk probe appends its trend samples. Cloud Run's filesystem is ephemeral per instance, so the trend resets on every cold start — acceptable for the demo board; a persistent volume is out of scope for this task. |

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
