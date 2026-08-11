DM1.7 (verification loop) is complete.

**What was built:** \`src/deadman/remediate/verify.py\` — \`verify_remediation(executor, probe, diagnosis, evidence, max_attempts=3)\`. After a wet-run remediation, it re-runs the *originating* probe (validated against the diagnosis's cited surfaces) via the same never-raise \`run_probe\` contract, and only a fresh \`Observation.HEALTHY\` counts as success. \`ActionResult.performed\` is never consulted. A probe going blind on re-run comes back \`UNOBSERVABLE\`, not success. Retries are bounded by \`max_attempts\`; exhausting it without a healthy reobservation returns \`EXHAUSTED\` rather than looping forever, and an immediate escalation (nothing performed) returns \`NOT_ATTEMPTED\`.

**Verification:** 8 new tests (\`tests/test_remediate_verify.py\`), full suite 200/200 (up from 192), \`ruff check .\` clean, \`bpsai-pair arch check --strict\` clean. All four guards (HEALTHY-only success, escalation short-circuit, surface-match validation, attempt cap) were mutation-tested — each broke a specific named test when inverted, then restored.

**Not wired into \`service.py\`**, same reason as DM1.6/DM1.10 — no live executor/diagnosis engine is wired into the endpoint yet; DM1.12 is the integration point.

Task marked \`done\` via \`bpsai-pair task update DM1.7 --status done\` (strict AC gate passed), and \`.paircoder/context/state.md\` updated with the session record. Next up per state.md: DM1.12 (integration gate) is the only unblocked task remaining; DM1.8/DM1.11 still need a human with GCP access.