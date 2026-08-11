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
