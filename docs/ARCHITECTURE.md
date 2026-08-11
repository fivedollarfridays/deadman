# deadman — architecture

A dead man's switch for heterogeneous infrastructure. The absence of a signal
IS the signal.

## The thesis

Every surface here fails silently in a different way, and none of them publish
their own health. There is no metadata graph to read. So the hard problem is
not "is this stale" but **"what counts as evidence that this particular thing
is alive, when every thing is different?"**

## The line: deterministic vs inferential

| Layer | Deterministic | Model |
|---|---|---|
| **Detect** | ✅ free bytes, mtime, does post ID exist | |
| **Diagnose** | | ✅ read heterogeneous failure evidence, form causal hypothesis |
| **Select action** | ✅ closed table, cause → function | ✅ the model decides which evidence is causal; that choice is what changes the action |
| **Correlate** | | ✅ infer shared root cause across surfaces (no lineage graph exists) |
| **Execute** | ✅ re-queue, free cache, restart, failover | |
| **Verify fix** | ✅ same capture-evidence standard as detection | |

**The model never asserts a fact and never declares success.** It reasons over
evidence and chooses an action. Code proves the outcome. Otherwise the
remediation is just another heartbeat, which is the thing this argues against.

## How "never asserts a fact" is actually enforced

`deadman.diagnose` splits a model response into two kinds of content and
treats them completely differently.

| | Enforcement |
|---|---|
| **Facts** — the `citations` array | Each must be quoted **verbatim** out of the one piece of evidence it names. Checked per-evidence, so attributing the scheduler's 500 to the disk read fails. Unknown or hallucinated evidence ids fail. |
| **Hypothesis** — free prose | Allowed to be new text; that is the point. Never rendered or consumed as fact, and confidence is capped by the trust tier of the cited evidence, so a claim leaning on `REPORTED` cannot be held strongly. |

One failed citation discards the **entire** response — the hypothesis was
reasoned from the invented fact along with the rest, so keeping the survivors
would leave a conclusion on a premise that was thrown out. The result becomes
`DiagnosisStatus.UNGROUNDED`: zero confidence, `is_actionable` false, the
rejected text retained so a human can review what was refused.

Three statuses, for the same reason `Observation` has three. `UNGROUNDED`
("the model said something false") and `UNAVAILABLE` ("we could not read what
it said") are different facts and are never collapsed.

## Surfaces (v1)

| Surface | Capture evidence | Why it's interesting |
|---|---|---|
| **Metricool posting** | the post exists **on the platform**, not "scheduled" in Metricool | Scheduler status is a heartbeat. Known real incident: FWDAO roundtable post never published, uncaught. |
| **Disk** | free bytes **trend**, not threshold | Never crossed a line, drifted for weeks, then killed Docker on a deadline day. |
| **Phone/SMS relay** | a send **verified in the sent folder** | Silence is ambiguous: no traffic or dead rail look identical. Needs an **active canary**. |
| **Morning brief cron** | a send-log row | The control. Capture evidence already exists, proves the pattern generalises. |

## Why remediation is not a lookup table

A Metricool post that failed to publish:

- expired token → re-queue fails identically. Fix auth first.
- policy/caption rejection → re-queue is worse than nothing.
- transient 5xx → re-queue immediately.
- disconnected channel → re-queue to nowhere.

The action space is too wide to hardcode and the correct choice requires
understanding *why*. That is the agentic decision.

## How the model chooses without the model acting

`deadman.remediate` splits that decision in two, and the seam is the whole
design.

| | Who decides | On what |
|---|---|---|
| **Which evidence is causal** | the model | messy heterogeneous failure material — the thing a rule engine cannot read |
| **What that evidence means** | `remediate.cause` | status codes, error codes, probe-authored summaries. Rules written in advance, output a value from a closed enum |
| **What to do about it** | `remediate.registry` | a table from cause to a function that existed before the run |

No string a model produced is ever a key, an argument, or a body. A model that
hallucinates can push selection toward the wrong *registered* action; it cannot
reach an action nobody wrote. `Registry.register` refuses any callable with no
source file behind it, which is what an `exec`-built body looks like — that
stops the obvious route and is not a sandbox, and the module says so.

Every path that cannot establish all three refuses:

- the diagnosis was `UNGROUNDED` or `UNAVAILABLE` — acting on it would be
  acting on a fact the model made up, or on our own blindness;
- no rule recognised the failure. The tempting default is "probably transient,
  retry it", and that default is wrong in exactly the cases that matter;
- the cause is recognised and has **no action on purpose**. A policy refusal
  and a disconnected channel both escalate, because re-queueing is worse than
  doing nothing for one and delivers nowhere for the other;
- the confidence the cited evidence can carry is under the action's floor.
  Every floor sits above `Method.REPORTED`'s 0.4 ceiling, so a hypothesis
  leaning on a scheduler's "it published fine" can never move infrastructure;
- the capability the action needs is not wired up.

**Dry run is the default.** Selection, classification and reporting all happen;
the body does not. And an `ActionResult` says `performed`, never `success` —
whether the surface recovered is a fact about the surface, which only a fresh
observation establishes. That is the verification loop.

## The verification loop closes the honesty gap

`deadman.remediate.verify` is the layer allowed to say a fault is gone, and it
is the only one. `Remediation.result.performed` says a code path ran without
raising; it is a fact about this process, not about the surface, and
`verify_remediation` never reads it to decide success.

What it does read: the *same probe that reported the fault*, re-run through
the same never-raise contract (`run_probe`) detection uses. Only a fresh
`Observation.HEALTHY` counts. A probe that goes blind on re-run comes back
`UNOBSERVABLE`, not `HEALTHY` — being unable to tell whether a fix worked is
still not a fix, so that reports `EXHAUSTED`/unverified rather than success.

The probe has to be one the diagnosis actually cited — `verify_remediation`
checks the probe's surface against the diagnosis's evidence ids and refuses
an unrelated one, since re-observing the wrong surface would prove nothing
about the fault that was acted on.

Each attempt re-plans and re-executes against the same diagnosis and
evidence, because the world can change under the action even when the inputs
do not. That repeats only up to `max_attempts`: a surface still broken after
the cap is `EXHAUSTED`, never retried forever — the AC this guards is
"repeated failed remediation stops rather than looping".

## Correlating without a graph

A lineage-graph monitor answers "what else does this affect?" by walking edges
somebody declared. Nothing declares an edge between free bytes on a laptop
volume, a phone relay and a third-party scheduler; the surfaces share no schema
to build one from and nobody is going to write one. So `deadman.correlate`
**infers** the relationship, which is the harder half of the problem, and says
so on every incident it produces.

Two stages, and the split is the whole design.

| | Who decides | On what |
|---|---|---|
| **Which faults are worth one question** | `correlate.window` | `read_at` proximity. Deterministic, cheap, and establishes *nothing* |
| **Whether they share a cause** | the model, via `diagnose` | the same grounded-citation contract as any other hypothesis |
| **Which surfaces the incident covers** | `correlate.engine` | the citations — never the window |

**Co-occurrence is candidacy, not evidence.** Every probe in a sweep runs
within milliseconds of every other, so two faults share a `read_at` whether or
not they share a cause — and `read_at` is when *we looked*, not when the fault
began. Timing agreement earns the right to ask the question. Nothing more, and
in particular no confidence: the number on an incident is the diagnosis's own
capped number, carried through unchanged.

**Membership is read off the citations.** A model handed three broken things
will narrate a single story about them, and the story is free. So a
relationship requires quoted evidence from **two or more faulting surfaces**;
a surface that merely broke at the same time is not a member.

**Blindness is never a leg**, at either stage. An `UNOBSERVABLE` row beside a
lone fault is not a candidate, and a hypothesis that ties a fault to a blind
surface is not a correlation — `grounded-blind-relay-tie` is exactly that case,
fully grounded and still refused. A surface we could not see cannot corroborate
anything; inferring from it is inferring from an absence of evidence.

**What the incident does not explain is a section, not a footnote.** Faults and
blind spots in the window that the shared cause did not account for are listed
by name. They are deliberately *not* folded into a discount on the confidence:
turning "we could not see the relay" into a slightly smaller number tells a
reader we were less sure and never tells them of what.

Three statuses, for the same reason `Observation` and `DiagnosisStatus` have
three. `UNCORRELATED` ("we got an answer and it tied nothing") and
`UNAVAILABLE` ("we could not get an answer") never collapse — an operator told
"uncorrelated" concludes we checked.

`Basis.INFERRED` rides on every incident and is rendered in words, naming the
surfaces no edge was found between and stating what inference costs: it can be
wrong in ways a declared dependency edge cannot. `Basis.TRAVERSED` exists in
the enum and nothing in this repo can produce one; a test pins that.

## What crossing a wire does to a claim

The surfaces are not where the service is. Cloud Run cannot read a log on a
Mac, so a collector runs where the surfaces live and posts signed batches to
`POST /evidence` (`src/deadman/ingest/`). That topology has a consequence the
HTTP hides: **every observation the hosted service holds is a report of an
observation, not an observation.**

So arrival caps the method of every incoming row at `REPORTED`, the weakest
tier on the ladder. The collector's claimed method is preserved in
`detail.reported_method` rather than erased — downgraded, not discarded — but
nothing automated may read a relayed claim as more than a claim. Recording a
collector's file read as the service's own would have the service assert it
inspected a disk it has no access to: a heartbeat wearing a hat, which is the
exact construction `Method.REPORTED` was named to catch.

**What that costs is the point, not a bug to route around.** Every action
floor in `remediate/registry.py` sits above the 0.4 confidence ceiling
`diagnose/grounding.py` imposes on a `REPORTED` citation, so a diagnosis
resting only on collected evidence escalates to a human instead of moving
infrastructure. An agent that restarts a service on an unverified relayed
assertion is how automated remediation turns an outage into two.

Three more facts about a stored remote row, each a field rather than a
convention:

- `read_at` stays the collector's reading time and `detail.received_at` is
  ours. Collapsing them would date a spool delivered after an outage as a
  burst of readings taken *during* it.
- `detail.collector_id` names who said it — which DM2.4 needs, because on a
  wire an empty inbox and a healthy estate look identical, and telling them
  apart requires knowing who was expected to speak.
- `detail.wire_row_id` is the identity of the observation, computed before
  arrival is annotated. A collector that could not deliver re-sends, and it
  must be able to; deduplicating on the *stored* row would fail, because the
  stored row carries an arrival time that differs on the second delivery.
  Idempotency keyed on our own bookkeeping is not idempotency.

Auth fails closed at startup: no `DEADMAN_INGEST_SECRET`, no service. The
alternative failure is quiet — an endpoint accepting unsigned batches produces
a board that looks like a monitored estate and is a guestbook.

## The collector: where evidence actually gets produced

`src/deadman/collector/` is the other end of the wire the previous section
describes — the process that runs on Kevin's machines, sweeps whatever
probes a config file names, and ships a signed batch to `POST /evidence`.

**Which probes run is a fact about a file, not the collector's source.**
`collector/config.py` reads a JSON config naming probe types and their
arguments; `PROBE_TYPES` maps a type name to the real dataclass it
constructs, and argument coercion (string → `Path`) is read off the target
dataclass's own field annotations rather than hand-coded per probe. Adding a
surface on a new machine — a different disk, a different brief log — is a
new config file. A malformed one fails at startup naming the exact key that
is wrong, never a collector that starts and silently sweeps nothing.

**Probe isolation is inherited, not reimplemented.** The collector calls
`deadman.probes.base.sweep()` — the same never-raise contract detection
already relies on — so a probe that raises does not prevent the rest of the
sweep's evidence from shipping. There is no second version of that rule to
keep in sync with the first.

**Store-and-forward means exactly two outcomes for a row: shipped, or still
spooled.** A batch the transport could not deliver — unreachable, or a
non-200 reply — is written to a spool directory rather than discarded, and
a later run drains it, oldest first, before attempting its own fresh sweep.
Nothing about the spool lives in process memory: a `Spool` reconstructed
over the same directory after a crash sees exactly what the prior process
left behind, because the directory *is* the state.

**A resend is signed fresh, never replayed.** `deadman.ingest.auth` bounds
`signed_at` to a five-minute freshness window, and a spooled batch can sit
far longer than that while a network is down. Reusing the original
signature would make an honest retry look like a stale replay and fail the
exact check it should pass. So every send — first attempt or the tenth
retry — builds a new `Batch` at the current clock reading and signs that;
only `signed_at` changes, never the evidence rows' own `read_at`.

**Dry run proves this before it ships anything real.** `--dry-run` sweeps
and prints the batch that would be sent, and never calls the transport at
all — not "calls it against a mock", calls it *zero times* — which is what
lets a test assert the property under the suite's real hermetic socket
block instead of only against a fake.

**Two machines, same probe, distinct ids.** `host:mac/disk` and
`host:rig/disk` are both `DiskProbe`, differing only in a `host` config
argument, because a full volume on one machine says nothing about the
other and a shared surface id would let one machine's healthy report paper
over the other's fault. See `docs/surfaces.md` for the real path, cadence
and blindness meaning of every surface actually deployed, as opposed to the
abstract "Surfaces (v1)" table above.

## Deployment

Brain in **Cloud Run**. Collectors on each host push evidence outward. Actions
dispatched back. A monitor must not share fate with what it monitors.

Built with **Cloud Build**, so no local Docker daemon is required. The image
installs `.[firestore]`, because ingested evidence goes to a store that
outlives the instance — a memory-backed deploy would forget the estate on
every scale-to-zero, and forgetting is indistinguishable from never having
been told.
