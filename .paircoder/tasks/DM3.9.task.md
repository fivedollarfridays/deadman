---
id: DM3.9
title: Redact personal email, phone, home-path, and account-name data from public
  docs and fixtures
plan: plan-2026-09-dm3-9-redact-personal-details
type: chore
priority: P1
complexity: 3
status: done
sprint: null
tags: []
depends_on: []
complexity_scale: points
runtime:
  pre_task_sha:
    deadman-redact: 86780a45623e8e89a469622138d4101a6707081d
  conflicts_encountered: none
completed_at: '2026-09-27T17:44:56.529575+00:00'
---

# Objective

`docs/alerting.md` publishes the owner's personal Gmail address as the
`DEADMAN_ALERT_TO` example value, and carries stale notes about an old dummy
SMTP setup. A repo-wide grep of tracked files turns up the same personal
email address elsewhere, plus `/Users/<name>` and `/home/<name>` paths
naming the owner's real account, in a public repo. None of this is required
for the docs or fixtures to make their point; all of it is replaceable with
a placeholder or generic wording with no loss of meaning.

# Implementation Plan

1. `docs/alerting.md`: replace both personal email addresses with
   placeholders; rewrite the "Verification: blocked, not done" section so it
   describes today's alerting.py / transports.py behavior rather than a
   stale dummy-SMTP anecdote from a sibling repo.
2. Replace the remaining personal email address in
   `.paircoder/context/state.md` with a placeholder.
3. Replace every `/Users/<name>` and `/home/<name>` path naming the owner's
   real account (docs, task files, fixtures, tests) with a placeholder
   username, updating any test assertion that checks for the literal name
   so the behavior under test is unchanged.
4. Re-run the full suite and confirm no test asserts on a value being
   removed.

# Acceptance Criteria

- [x] `docs/alerting.md` contains no personal email address and its
      verification section matches current `alert.py`/`transports.py`
      behavior
- [x] `grep` of all tracked files finds no personal email addresses (other
      than placeholders/noreply), phone numbers, or `/Users/<name>` /
      `/home/<name>` paths naming the owner's real account
- [x] Full test suite passes
- [x] `bpsai-pair arch check` clean on modified files

# Verification

- `git grep` for email/phone/home-path patterns across tracked files
  returns only placeholders
- `pytest -n auto --dist=worksteal` green
- Docs still read correctly after substitution