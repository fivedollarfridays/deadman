# Verifying the live Gemini path

The diagnosis layer is the one place in deadman that talks to a model, and it
is the one place the hermetic test suite cannot cover. Everything downstream
of the model is exercised offline against recorded responses; the call itself
has to be proven by hand, once, against the real thing.

Contest eligibility depends on it. The rules require Gemini reached through
the ADK, so an untested call shape is not a code-quality concern, it is an
entry that does not qualify.

This document records the run that proved it and the two things that stood in
the way, both of which fail in ways that point somewhere unhelpful.

## Result

Verified 2026-08-10 against project `deadman-20260810`.

```
model      : gemini-3.5-flash
confidence : 0.6
hypothesis : The cron:morning-brief surface is in a 'fault' state as there has
             been 'no brief sent in 218.4h (window 30h, ~9 missed)'. Although
             the host disk is 'healthy' with '41.2GB free, 9 days of runway',
             the available evidence is insufficient to determine the
             underlying cause of the cron job's silent failure.
cites      : ('cron:morning-brief#92a5ad02', 'host:disk/#5266c156')
```

Read that hypothesis closely, because it is the most valuable thing the smoke
test produced. It was handed a real fault and it declined to name a cause,
saying the evidence does not support one. The grounding rules in
`deadman.diagnose.engine` are enforced offline against fixtures we wrote
ourselves, which only ever demonstrates that our fixtures obey our rules.
This is the first evidence that a real model, given a real fault with no cause
present in the evidence, does not manufacture one.

It also cited both evidence ids rather than the one it ruled on, which is the
behaviour the citation contract asks for: say what you read, not just what you
concluded from.

A second run went further and used the healthy surface as evidence *against* a
hypothesis: "it is not due to disk space exhaustion as the host disk is
healthy with 41.2GB free, 9 days of runway." That is the reasoning the
correlation layer exists to support, and it is worth noting that it fell out
of the evidence format without being asked for. A healthy surface is not
noise; it narrows the field.

Both runs held the same line on the part that matters. Neither invented a
cause.

## Gotcha 1: gemini-3.5-flash is global-only

`gemini-3.5-flash` is served **only from the `global` Vertex endpoint.**

```
global       gemini-3.5-flash     OK
global       gemini-2.5-flash     OK
us-central1  gemini-3.5-flash     404 NOT_FOUND
us-central1  gemini-2.5-flash     OK
```

Every 3.x id 404s in `us-central1`, while 2.5 works in both. The natural
instinct is to match `GOOGLE_CLOUD_LOCATION` to the Cloud Run region, and here
that instinct silently downgrades you to a model the contest does not accept,
or breaks the call outright. Set `global` for the diagnosis path specifically.

A 404 on a model id reads like a wrong or retired name. It is worth probing
`global` before concluding the name is wrong.

## Gotcha 2: a fresh service account 403s before it 200s

The IAM binding takes up to a minute to take effect, and during that window
every call returns `403 PERMISSION_DENIED` on `aiplatform.endpoints.predict`.
That is indistinguishable from a genuinely missing role.

Verify the binding actually exists before you start changing it:

```bash
gcloud projects get-iam-policy PROJECT_ID \
  --flatten='bindings[].members' \
  --filter='bindings.members:deadman-vertex' \
  --format='value(bindings.role)'
```

If that prints `roles/aiplatform.user`, the grant is correct and you are
waiting on propagation, not debugging permissions. Retry for two minutes
before touching anything.

## Setup

Credentials, without a browser OAuth flow. `gcloud auth application-default
login` needs an interactive paste; a service account key does not.

```bash
PROJECT_ID=your-project
gcloud iam service-accounts create deadman-vertex \
  --display-name="deadman Vertex AI" --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:deadman-vertex@$PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/aiplatform.user

mkdir -p ~/.deadman-creds && chmod 700 ~/.deadman-creds
gcloud iam service-accounts keys create ~/.deadman-creds/vertex-sa.json \
  --iam-account=deadman-vertex@$PROJECT_ID.iam.gserviceaccount.com
chmod 600 ~/.deadman-creds/vertex-sa.json
```

That key is a long-lived credential. It lives outside the repo, is never
committed, and should be deleted when the contest is over:

```bash
gcloud iam service-accounts keys list \
  --iam-account=deadman-vertex@$PROJECT_ID.iam.gserviceaccount.com
gcloud iam service-accounts keys delete KEY_ID \
  --iam-account=deadman-vertex@$PROJECT_ID.iam.gserviceaccount.com
```

Environment, noting the `global` location:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=$HOME/.deadman-creds/vertex-sa.json
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=$PROJECT_ID
export GOOGLE_CLOUD_LOCATION=global
```

Required APIs: `aiplatform.googleapis.com`.

## Repeating the smoke test

```bash
pip install -e '.[gemini]'
python scripts/gemini_smoke.py
```

The script builds two pieces of `Evidence` by hand, one fault and one healthy,
runs them through `DiagnosisEngine` with a real `GeminiClient`, and prints the
model, confidence, hypothesis and citations. It is deliberately not a test:
the suite blocks sockets, and this needs one.

Run it before the demo. The call shape is the only part of this system whose
correctness rests on a document rather than on a passing assertion.
