## Summary

DM2.6 is implemented and code-complete, but landed as **\`blocked\`**, not \`done\` — the strict AC gate correctly refused completion on two ACs that need live GCP access this sandboxed worktree doesn't have.

**What's done and verified:**
- \`POST /self-check\` — a new authenticated endpoint (\`src/deadman/scheduled/\`), separate from the public \`GET /\` board, using a bearer-token secret (\`DEADMAN_SCHEDULER_SECRET\`) mandatory at import — mirrors the existing \`DEADMAN_INGEST_SECRET\` doctrine exactly.
- Self-check evidence now writes through the DM2.1 store (\`StoreSelfEvidenceLog\` in \`src/deadman/self_check.py\`), not a per-instance file — retiring DM1.11's cold-start limitation. \`self_check()\`/\`run_self_check()\` were generalized via a \`SelfEvidenceSink\` Protocol so they work against either sink unchanged.
- Tests prove: unauthenticated requests are rejected and store nothing; a second, independently-built app instance (sharing only the store) reads what the first wrote — the actual cold-start proof; the endpoint isn't the board.
- Collector-vs-Cloud-Scheduler independence documented in \`infra/scheduler.md\`.
- Gates: 528/528 tests, \`ruff check\`/\`ruff format --check\` clean, \`arch check --strict\` clean.

**What's blocked:** enabling the Cloud Scheduler API + creating the job, and verifying it actually fired (via a stored row). This environment has no \`gcloud\` CLI and no ADC configured at all — I checked before writing anything rather than faking it. \`infra/scheduler.md\` has the exact, reproducible commands, same discipline as DM1.8's and DM2.7's blockers.

**One thing to act on before the next deploy:** the service now refuses to import without \`DEADMAN_SCHEDULER_SECRET\`, so it needs to be set on the live Cloud Run service (step 1 in \`infra/scheduler.md\`) *before* the next \`gcloud builds submit\`, or that redeploy takes the currently-live service down.

state.md, the task file, and Blockers are all updated. Let me know if you'd like me to walk through the \`infra/scheduler.md\` commands with you (you'd need \`gcloud\` authenticated for \`deadman-20260810\`), or if you want to run them yourself from the rig like DM1.8's deploy.