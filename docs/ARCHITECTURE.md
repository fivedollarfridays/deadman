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
| **Select action** | | ✅ the right remediation depends on the diagnosis |
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

## Deployment

Brain in **Cloud Run**. Collectors on each host push evidence outward. Actions
dispatched back. A monitor must not share fate with what it monitors.

Built with **Cloud Build**, so no local Docker daemon is required.
