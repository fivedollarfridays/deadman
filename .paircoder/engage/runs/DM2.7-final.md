All gates clean. Everything is in place; I have not committed anything since that wasn't requested. Here's a summary of the session's work:

## Summary

**DM2.7 is \`blocked\`, not \`done\`** — one AC could not be honestly satisfied.

**Built and fully verified (TDD, mutation-checked, all gates green):**
- \`src/deadman/remediate/transports.py\` — \`EmailTransport\` (stdlib SMTP+STARTTLS, matching \`ops/lib/email_send.py\`'s shape), \`email_transport_from_env\` (six \`DEADMAN_ALERT_*\` vars, no hardcoded credentials), \`real_monitored_surfaces()\` (sourced from the actual live probe list, not a retyped literal), \`ThrottledAlertChannel\` (1h documented window, never suppresses a state change), \`record_transport_failures\` (records to the DM2.1 evidence store, still re-raises).
- \`tests/test_transports.py\` — 20 new tests, all passing on first run; the two behavior-critical guards (state-change delivery, failure-not-swallowed) were manually mutation-checked.
- \`docs/alerting.md\` — documents the rail, throttle window, out-of-band rationale, and wiring status.
- Fixed a pre-existing, unrelated bug in \`tests/test_ingest_startup.py\` that was blocking the mandatory full-suite gate (its own docstring's RST markup was tripping its own secret-scan regex).

**Blocked on:** "one real message is confirmed received." Before writing anything I checked whether \`ops\`'s SMTP rail actually works — it doesn't. \`ops/.env\`'s SMTP block is explicitly commented \`# DUMMY SMTP — for T87.2 testing only. Real sends will fail at connect\`, and \`ops\`'s own alertmanager config and backlog (\`T152-outbound-email-rail\`) confirm real email delivery isn't live there yet. That's a fact about a sibling repo, not a defect in this code — so rather than fabricate a "confirmed received" claim, I documented the finding and left a one-time verification script in \`docs/alerting.md\` for once real credentials exist.

Task file, \`state.md\`, and task status (\`blocked\`) are all updated to reflect this honestly. DM2.3/DM2.4 (next wave) aren't blocked by this.