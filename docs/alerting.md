# Alerting: the rail, the backoff, and why both are safe

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
| `DEADMAN_ALERT_TO` | where the alarm goes — the owner's address |

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

### Rails are spelled; transports are real

A rail prefix is only as good as the name somebody typed. The morning brief's
surface id is `cron:morning-brief`, and it is sent by ops over an SMTP account;
the alarm is `email:...`, and this document tells you to point it at the same
account. `cron` versus `email` passes the prefix check, and one expired
credential then kills the brief and its alarm together, which is the outage
in `PROOF.md` one layer down.

So the channel also compares real transports. `EmailTransport.identity` is
`smtp:<host>/<account>`, built from the SMTP host and login it actually sends
with. A monitored surface declares the transport it depends on in the
collector declaration's optional `transports` object (see `infra/README.md`,
including why a declared account is published in plain text). `AlertChannel` raises `AlertChannelInvalid`
at construction when its identity matches any declared transport, whatever
either is named, and `default_alarm` lets that propagate: the service refuses
to boot, as documented above, instead of degrading to "unconfigured".

**The check is only as complete as the declaration.** A surface whose
transport is not declared cannot be compared, so the committed
`infra/collector/collectors.json` declares none today and the live alarm is
not refused by it. Declaring the morning brief's real account is the owner's
decision, and if the alarm shares that account, the deploy will refuse
to start until the alarm moves to a different one.

## The backoff: one incident pages a few times, on any instance

From 2026-10-09 to 2026-10-11 one ongoing fault sent 39 alert emails in about
45 hours, roughly one an hour, and all of them sat unread. The repeat throttle
at the time was one hour long and lived in instance memory, so a Cloud Run
cold start also forgot it. An alarm that repeats hourly teaches its owner to
ignore the thread. DM4.1 replaced it with `DurableBackoffAlarm`
(`src/deadman/scheduled/backoff.py`), which is what
`deadman.scheduled.alerting.alarm_from_env` now returns and what every
`POST /self-check` runs.

**The schedule is one constant, `BACKOFF_SCHEDULE`: 6 hours, 12 hours, then
24 hours.** It is the ops freshness monitor's schedule on purpose.

| Alert | Sent at | Step |
|---|---|---|
| first | 0 h, at once | |
| repeat 1 | 6 h | 6 h after the first |
| repeat 2 | 18 h | 12 h after that |
| repeat 3 | 42 h | 24 h after that |
| repeat 4 and on | 66 h, 90 h, ... | every 24 h |

A fault held for 48 hours is 4 emails. The old behaviour sent about 40.

**Episodes.** An episode opens when a surface first alerts, or when its alert
state changes. The first alert of an episode always sends at once. A state
change inside an open episode (`stale` to `fault`, say) is a new fact: it
sends on that sweep and restarts the schedule from there. A heal closes the
episode and sends exactly one recovery notice, and only if the surface had
alerted; a surface that was never in trouble sends nothing, cold start or
not. A fault after a heal is a new episode and sends at once, however soon.

**The send record is durable.** What was sent for a surface, and when, is one
overwritten record per surface in the evidence store, read and written
through `EvidenceStore.load_alert_state` and `save_alert_state`. On the
deployed service that is the Firestore document `alert_state/<surface key>`
(the key is the surface id percent encoded once, the same `surface_key` the
evidence rows use). It holds `state`, `episode_started_at`, `last_sent_at`,
`sends` and `open`. The alarm object keeps nothing between calls and reads the
record on every decision, so an instance that booted a second ago decides
exactly as a warm one does. The collection is separate from `evidence`, so a
send record never appears as a row on the board or in `undeclared_surfaces`.

**The decision is "is a repeat due and not yet sent".** The next repeat is due
one schedule step after the last alert that was actually sent. A sweep that
arrives late (the 6 h mark missed, the next sweep at 7 h) still sends that
repeat, once, and the following step is measured from the late send.

**Every alert says when the owner will hear again.** The first alert of an
episode ends with the next repeat time. A repeat also states how long the
surface has held the state:

```text
deadman: service:staging-queue is fault — queue has not drained in 7200s

Still fault: held for 18h, first alerted 2026-10-09 14:00 UTC. This is repeat 2.
If it does not heal, the next repeat is due 2026-10-11 08:00 UTC (in 1d).
```

**What happens when the record itself fails.**

- *It cannot be read or parsed.* The alarm cannot tell whether it already
  spoke, so it speaks: the alert is sent, its body says repeats are not being
  limited, a `FAULT` row is appended to the evidence store on
  `alert:send-record`, and a fresh record is saved (which repairs a malformed
  document, so one bad record does not page forever). While a backend stays
  unreadable this sends on every sweep. That is deliberate: loud is the
  direction to fail in.
- *It cannot be read for a healthy surface.* No recovery notice is sent,
  because "recovered" for every healthy surface on every sweep would be an
  alarm about nothing. The failure is recorded on `alert:send-record`.
- *It cannot be written.* The alert already went out; the failed write is
  recorded on `alert:send-record` and the next sweep sends again.
- *The send itself fails.* Unchanged: recorded on `alert:email`, then raised
  (next section). The record is written only after a successful send, so an
  alert that never left is not counted, and the next sweep retries it.

`alert:send-record` and `alert:email` are not declared by any collector, so a
row on either shows up in the board's `undeclared_surfaces`. That is the only
place they appear, and it is meant to be seen.

**Known limit.** Two sweeps that overlap (a retried Cloud Scheduler attempt
racing the original) can both read the record before either writes it, and
both send. That is one duplicate of a true alarm.

`tests/test_alarm_backoff_schedule.py` pins the schedule with a brand new
alarm on every sweep, against both store backends;
`tests/test_service_alarm_wiring.py` pins it through
`deadman.service.default_scheduled` and an authenticated `POST /self-check`.

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

Wired. `deadman.service.default_scheduled` builds the alarm with
`deadman.scheduled.alerting.default_alarm`, and
`ScheduledSelfCheckEndpoint.handle` runs `evaluate` over every sweep that
`POST /self-check` triggers. The pieces are `EmailTransport`,
`email_transport_from_env`, `real_monitored_surfaces`,
`record_transport_failures` (this module) and `DurableBackoffAlarm`
(`src/deadman/scheduled/backoff.py`). The daily CLI,
`deadman.self_check.run_self_check`, still calls `channel.alert(message)`
directly with no backoff: it runs once a day, which is its own cadence.

## Verification: confirmed against a real account

Earlier drafts of this document recorded this acceptance criterion as
blocked, because the SMTP account the alarm was scoped against was still a
dummy setup in a sibling repo, one layer above deadman, that this project
does not own. That has since closed, per the acceptance-criteria record in
`.paircoder/tasks/DM2.7.task.md`: two real messages were sent through a
working SMTP account and confirmed received — one through the sibling
repo's own send helper directly, and one through deadman's own
`EmailTransport` via `email_transport_from_env`, with `DEADMAN_ALERT_*`
mapped onto that account's values. Channel construction succeeded because
email is not a monitored rail.

`EmailTransport` and `email_transport_from_env` are written and tested
against a standard STARTTLS-then-login-then-`send_message` shape, so no
deadman code stands between "the rail works" and "one real message is
confirmed received." To repeat the check against any working SMTP account:

```bash
export DEADMAN_ALERT_SMTP_HOST=...        # a real, working SMTP host
export DEADMAN_ALERT_SMTP_PORT=587
export DEADMAN_ALERT_SMTP_USER=...
export DEADMAN_ALERT_SMTP_PASSWORD=...
export DEADMAN_ALERT_FROM=...
export DEADMAN_ALERT_TO=you@example.com

python3 -c "
from deadman.remediate.transports import email_transport_from_env
email_transport_from_env().send('deadman alert channel verification')
"
```

A clean exit means the send succeeded (a rejected or misdelivered message
raises, per the "failures propagate" contract); then confirm the message
landed in the inbox by hand. The transport does not care which mailbox it
is, only that STARTTLS, login and `send_message` succeed against it.
