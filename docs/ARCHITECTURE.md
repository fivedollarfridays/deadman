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

## Deployment

Brain in **Cloud Run**. Collectors on each host push evidence outward. Actions
dispatched back. A monitor must not share fate with what it monitors.

Built with **Cloud Build**, so no local Docker daemon is required.
