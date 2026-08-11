"""The inferential layer.

Detection is deterministic and lives in :mod:`deadman.probes`. Diagnosis is
not: reading a disk trend, an HTTP 500 body and a dead SMS canary and saying
"one thing caused all three" is inference, and it is the reason this is an
agent rather than a cron job.

The line this package holds: **the model may infer, it may not invent.** See
:mod:`deadman.diagnose.grounding`.
"""
