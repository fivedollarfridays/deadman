# Alerting: the rail, the throttle, and why both are safe

DM1.11 built `AlertChannel`: a construction-time refusal to sit on any rail
deadman watches. It was never wired to anything real. This is the module that
makes it real — `src/deadman/remediate/transports.py` — and this document is
the thing `test_ingest_startup.py`'s own lesson says a runbook must be:
executed, not assumed.

## The rail: email, over the same SMTP account the ops repo already uses

The transport is plain SMTP with STARTTLS, sent via stdlib `smtplib` and
`email.message.EmailMessage` — no new dependency, so `pyproject.toml` keeps
`dependencies = []`. The shape (`starttls()`, then `login()`, then
`send_message()`) deliberately matches `ops/lib/email_send.py`'s
`send_email`, because this is meant to go out over the mailbox Kevin already
watches, not a second inbox nobody checks.

`email_transport_from_env` reads six variables and refuses to construct a
transport — raising `EmailTransportNotConfigured` — if any are missing:

| Variable | Meaning |
|---|---|
| `DEADMAN_ALERT_SMTP_HOST` | SMTP server host |
| `DEADMAN_ALERT_SMTP_PORT` | SMTP port (587 for STARTTLS) |
| `DEADMAN_ALERT_SMTP_USER` | SMTP auth username |
| `DEADMAN_ALERT_SMTP_PASSWORD` | SMTP auth password |
| `DEADMAN_ALERT_FROM` | envelope/header `From` |
| `DEADMAN_ALERT_TO` | where the alarm goes — Kevin's address |

These are deadman's own names, distinct from the ops repo's generic
`SMTP_HOST`/`SMTP_USER`/`SMTP_PASS`/`SMTP_FROM` — a deploy of deadman does not
share a process environment with the ops repo, so borrowing its variable
names would either collide with an unrelated value or silently read nothing.
Set them to the *same underlying account* ops already uses; that is what
makes this "the existing ops rail" rather than a second mail setup to
provision and forget. **No credential has a default and none is committed** —
`EmailTransport`'s `host`/`username`/`password`/`from_addr`/`to_addr` fields
have no default value, so a caller that forgets one gets a construction-time
`TypeError` or `EmailTransportNotConfigured`, never a silent empty string.

## Why this rail is out of band

Every surface deadman watches lives on one of four rails: `cron`
(morning-brief), `host` (disk), `sms` (relay), `metricool`. `email` is a
fifth, unrelated rail — no probe reads it, so nothing that can put the
alarm's own rail into a fault state is itself being monitored by that alarm.

That is necessary but not sufficient, which is why the check is not "is the
transport literally `email:...`" but a real comparison against
`real_monitored_surfaces()` — the exact probe list
`deadman.service.default_probes()` runs, not a hand-typed copy of it.
Constructing an `AlertChannel` whose transport shares a rail with anything in
that list raises `AlertChannelInvalid` at construction, before the channel
can ever be handed to code that might rely on it. `real_monitored_surfaces()`
is read from the probes themselves for exactly this reason: a literal list
can go stale the moment a new probe ships, silently letting a future
monitored rail double as the alarm. Reading it from the live probe objects
means the check can never fall behind what is actually watched.

## The throttle: a documented window, and one absolute exception

A persistent fault sweeps on every cadence — the morning brief will still be
dead on sweep two, three, and every sweep after that until someone fixes it.
Resending an identical alert on every sweep is alarm fatigue by construction,
so `ThrottledAlertChannel` suppresses a **repeat of the same state** for a
caller-scoped key within `DEFAULT_THROTTLE_WINDOW` (one hour).

The one thing it will never suppress: **a state change.** Fault-to-healthy or
healthy-to-fault always sends immediately, however recently the last alert
fired for that key. A throttle that could swallow a transition would be worse
than no throttle at all — silence around the one moment silence is
unaffordable. `tests/test_transports.py` pins this by flipping state
mid-window and asserting every message still arrives.

```python
channel = ThrottledAlertChannel(channel=alert_channel)  # window defaults to 1h
channel.alert("cron:morning-brief", "fault", "no brief sent in 36h")  # sends
channel.alert(
    "cron:morning-brief", "fault", "no brief sent in 42h"
)  # suppressed — same state, inside the window
channel.alert("cron:morning-brief", "healthy", "brief sent")  # sends — state changed
```

## A transport failure is evidence, not silence

`record_transport_failures` wraps a `send` callable: if it raises, the
failure is appended to the DM2.1 evidence store as a `FAULT` row on
`alert:email` (`Method.ACTIVE_CANARY` — the send attempt itself is what
exercises the rail end to end) before the exception is re-raised. The raise
is not removed; `AlertChannel.alert`'s contract that "a swallowed alert is
silence" still holds. Recording is additional: it means a broken mail rail
leaves a trace on the board even though the alert it was trying to send did
not arrive.

## Wiring status

This task delivers the pieces — `EmailTransport`, `email_transport_from_env`,
`real_monitored_surfaces`, `record_transport_failures`,
`ThrottledAlertChannel` — fully tested. It does not add a call site in
`src/deadman/service.py`: the file collision matrix in
`docs/SPRINT-BRIEF-DM2.md` keeps `service.py` out of this task's file list on
purpose, and the natural call site is DM2.6's scheduled self-check, which
does not exist yet. `deadman.self_check.run_self_check` still calls
`channel.alert(message)` directly (DM1.11's shape); routing it through
`ThrottledAlertChannel.alert(key, state, message)` with a real
`email_transport_from_env()`-backed `AlertChannel` is DM2.6's wiring, once the
scheduled cadence that would make throttling matter actually exists.

## Verification: blocked, not done — the ops rail has no working credentials yet

This is the one acceptance criterion this task could not close, and it is
recorded here rather than faked, per this project's own rule that a runbook
nobody has executed is a hypothesis (the lesson DM1.8's live-deploy blocker
already cost once).

Checked before writing this section: `ops/.env`'s active `SMTP_HOST` /
`SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` block is labelled in
its own comment **"DUMMY SMTP — for T87.2 testing only. Real sends will fail
at connect."** The real values it would use in production
(`kevinmasterson@bpsaisoftware.com`, port 587) are present only as a
commented-out fallback, never activated. `ops/monitoring/alertmanager/alertmanager.yml`
confirms independently: every receiver posts to a `localhost` webhook, with
`# In production, add: ... Email to on-call team` left as a TODO. There is a
standing ops backlog item for exactly this
(`backlog-sprint-T152-outbound-email-rail.md`). **The "existing ops email
rail" this task was scoped against does not yet exist as a working,
deliverable rail** — it is provisioned but inert, one layer up from
deadman, in a sibling repo this task does not own.

`EmailTransport` and `email_transport_from_env` are written and tested
against exactly the shape `ops/lib/email_send.py` uses (STARTTLS, login,
`send_message`), so no deadman code stands between "the rail works" and "one
real message is confirmed received." Closing this AC for real is a one-time
manual step once real credentials exist, not a code change:

```bash
export DEADMAN_ALERT_SMTP_HOST=...        # a real, working SMTP host
export DEADMAN_ALERT_SMTP_PORT=587
export DEADMAN_ALERT_SMTP_USER=...
export DEADMAN_ALERT_SMTP_PASSWORD=...
export DEADMAN_ALERT_FROM=...
export DEADMAN_ALERT_TO=kmasty1@gmail.com

python3 -c "
from deadman.remediate.transports import email_transport_from_env
email_transport_from_env().send('deadman alert channel verification')
"
```

A clean exit means the send succeeded (a rejected or misdelivered message
raises, per the "failures propagate" contract); then confirm the message
landed in the inbox by hand. Do this once T152 lands a real ops SMTP account,
or point `DEADMAN_ALERT_*` at any other working account in the meantime —
the transport does not care which mailbox it is, only that STARTTLS, login
and `send_message` succeed against it.
