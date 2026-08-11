# The demo

One take, start to finish, nothing edited.

```bash
pip install -e '.[gemini]'
python scripts/demo.py --live
```

Rehearsed runtime: **4.6s to 10.5s**, measured across four live runs on
2026-08-11. Everything except the Gemini call is effectively instant; the
spread is entirely model latency.

## What is real and what is not

Real: the probe, the evidence model, the Gemini call through the ADK, the
grounding rules, cause classification, action selection, the executor, the
verification loop, the self-check, the alert channel. All shipped code, none
of it special-cased for the demo.

Simulated: **the phone relay only.** A carrier outage cannot be arranged on
demand, so the one thing that cannot be broken on command is the one thing
injected, through the same `RelayClient` seam the probe already exposes for
tests. The failure it reports, an HTTP 503 from the relay host, is a shape
that rail genuinely produces.

Say this out loud during the take. A demo that hides its stub is doing the
thing this project exists to argue against.

## The sequence

**1. Healthy.** A canary goes out and is confirmed in the sent folder.

**2. Break it.** The relay starts answering 503. Nothing notifies deadman.

**3. Detected.** The next sweep manufactures its own evidence rather than
waiting for traffic. Worth narrating: silence on this rail is ambiguous, since
no traffic and a dead rail look identical from outside. The probe never infers
health from quiet.

**4. Diagnose.** Live Gemini reads the unstructured detail and returns a
hypothesis, a confidence and citations quoted out of the evidence.

**5. One fault is not a pattern.** The correlator declines to invent a
relationship. Co-occurrence is the entire basis for inferring a shared cause,
and a single fault has none.

**6. Select.** Deterministic and keyed on the diagnosed *cause*, not the fault.
A 5xx earns an immediate retry. An expired credential would not, because
re-queueing on a dead credential fails identically and burns the rate limit.

**7. Act, then prove it.** The executor returning success proves the code ran.
It does not prove the rail recovered. The probe is re-run, and only a fresh
`HEALTHY` observation counts.

**8. Who watches the watcher.** Self-liveness from a row written after a sweep,
not a heartbeat. The alarm refuses at startup to sit on any monitored rail.

## The honest part: it does not heal every time

Across four live rehearsals:

| run | diagnosis | confidence | verification | wall |
|---|---|---|---|---|
| 1 | grounded | 0.85 | verified | 4.6s |
| 2 | grounded | 0.85 | verified | 7.8s |
| 3 | grounded | 0.85 | verified | 7.0s |
| 4 | **ungrounded** | 0.0 | not attempted | 10.5s |

On run 4, Gemini returned a hypothesis that read correctly and cited nothing.
The grounding layer threw it out, and because nothing was grounded, nothing was
allowed to select an action. The demo prints that outcome as a completion, not
a failure, because it is the system working exactly as designed.

**Do not re-roll it if it happens on camera.** Narrate it. An agent that
refuses to act on its own model's uncited assertion is the entire argument,
and no scripted success demonstrates it half as well.

Roughly one run in four, on this evidence, with this model, at temperature 0.

## What rehearsal caught

The fourth outcome used to crash. `verify_remediation` raised `ValueError`
when the diagnosis cited nothing, because its guard could not distinguish
"the caller passed an unrelated probe", which is a programmer error worth
being loud about, from "every citation was rejected", which is ordinary
reality on a non-deterministic model.

A monitor that dies whenever its model has an off moment has become the
outage it was watching for. It now returns `NOT_ATTEMPTED`. See
`tests/test_remediate_verify_ungrounded.py`.

That defect was reachable only by running the thing live, more than once.
It is the argument for the rehearsal requirement in one bug.

## Rehearsing without spending a call

```bash
python scripts/demo.py            # scripted stub, no network, deterministic
```

The stub reads the evidence ids back out of the prompt and returns a
correctly-shaped response. It is not a model and does not pretend to be one;
it exists because the demo mints a fresh canary token every run, so no static
recording can ever cite ids that resolve. Use it to rehearse the sequence and
to prove the pipeline. Use `--live` for the take.

## The deployed service

```bash
curl https://deadman-mrapac5nda-uc.a.run.app/
```

Public, scales to zero, and returns the board. Worth showing on camera as the
Google Cloud requirement, and worth reading closely: `healthy_count` is 1 of 2
surfaces, and the second is `unobservable` rather than healthy, listed under
`blind_spots`. A threshold monitor would call that a clean run.

Which commit is serving is answerable, not assumed:

```bash
gcloud run services describe deadman --region=us-central1 \
  --format='value(spec.template.spec.containers[0].image)'
```

The tag is the commit SHA.
