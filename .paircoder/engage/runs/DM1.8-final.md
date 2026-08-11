Everything is in order. Here's the summary.

## Summary

DM1.8 is **blocked**, not done — deliberately. I built and locally verified everything that doesn't require live GCP credentials, and stopped at the one step this environment genuinely cannot perform.

**Done and verified:**
- \`src/deadman/service.py\` — dependency-free WSGI app publishing the current board (\`sweep()\` + \`blind_spots()\` over \`DiskProbe\`/\`MorningBriefProbe\`), built TDD-first. \`tests/test_service.py\`: 8 new tests, suite now 47/47.
- \`Dockerfile\` + \`.dockerignore\` — **actually built and ran** with the local Docker daemon (which turned out to be working, contrary to the stale sprint-brief note) and confirmed via \`curl\` that the containerized service returns the board correctly, including an honest \`unobservable\` blind spot for the unmounted brief log.
- \`cloudbuild.yaml\` — build/push run on Cloud Build's own workers (\`gcr.io/cloud-builders/docker\`), never a local daemon; deploy step via the Cloud SDK builder. Structurally validated.
- \`infra/README.md\` — project setup, required APIs, deploy command, URL lookup/verification, env var config.
- Gates: \`ruff check .\`, \`pytest tests/\` (47/47), \`bpsai-pair arch check --strict\` all clean.

**Blocked:** the two ACs requiring an actual live deploy (reachable Cloud Run URL; fresh-clone reachability). This worktree has no \`gcloud\` CLI and no GCP credentials anywhere on the machine — I checked \`PATH\`, \`~/.config/gcloud\`, \`~/google-cloud-sdk\`, and Homebrew casks. A real deploy is billable and hard to reverse, so I didn't attempt to fake around the gap. \`bpsai-pair task update DM1.8 --status done\` correctly refused via the strict AC gate; I set it to \`status: blocked\` instead and documented the specific unblock action in \`state.md\`.

**Next step is yours:** run \`gcloud builds submit --config cloudbuild.yaml .\` from a machine with GCP credentials (steps are in \`infra/README.md\`), then hand me the resulting URL so I can check the last two boxes and close DM1.8.