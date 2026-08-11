DM2.2 is done — all 10 acceptance criteria verified through the strict gate, committed as \`c5df8f0\`.

## What shipped

\`src/deadman/ingest/\` — four modules behind \`POST /evidence\`, wired into \`service.py\`:

- **\`arrival.py\`** — the rule the task exists for. Arrival caps every method at \`REPORTED\`, via a table that's total over \`Method\` so a method added later must be graded deliberately rather than by a silent default. The collector's claim survives in \`detail.reported_method\`.
- **\`auth.py\`** — HMAC over the raw bytes, verified *before* parsing; \`signed_at\` lives inside the signed payload, so the freshness window isn't decorative; secret from env, refusal on absence.
- **\`wire.py\`** — the store's document format plus an envelope, with strict decoding because the input is remote.
- **\`endpoint.py\`** — ordered so every refusal returns before any write.

## Two things worth your attention

**Automated remediation is now disabled on collected evidence, by construction.** Every action floor in \`remediate/registry.py\` sits above the 0.4 confidence ceiling a \`REPORTED\` citation earns. Since every real DM2 surface is remote, a diagnosis resting only on collected evidence escalates to a human instead of acting. I believe that's the correct reading of what the service knows, and it's documented in \`arrival.py\` and \`ARCHITECTURE.md\` — but it's a consequence you should see now rather than discover in DM2.9.

**DM2.1's handoff note was wrong on one point, and I've corrected it in state.md.** Idempotent replay was *not* free from content-addressed \`row_id\`: an arriving row must carry an arrival time, which changes the hash on every delivery, so the store's dedupe would never have fired on a re-sent batch. Ingest dedupes on \`detail.wire_row_id\` — identity computed before annotation. There's one named limit: the lookback is 200 rows per surface, and a replay older than that stores a *recognisable* second copy rather than a silent doubling.

## Not done here

The deploy is unrun — no \`gcloud\` in this session, and it's DM2.6's privileged step. I closed the deploy path (\`.\[firestore\]\`, \`DEADMAN_STORE_BACKEND=\[REDACTED_ENV\] via \`--update-env-vars\`, never \`--set-env-vars\`, which would wipe the ingest secret every build) and documented the Firestore prerequisites, but DM2.6 must verify the database exists, the service account holds \`roles/datastore.user\`, and the secret is set. All three fail closed at startup, so a bad deploy will be loud.

Gates: 342 passed (from 265), ruff clean both ways, \`arch check --strict\` clean. Ten mutations tested, ten caught — including one that removes the downgrade at the endpoint while leaving every arrival unit test green.