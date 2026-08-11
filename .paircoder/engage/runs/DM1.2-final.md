**DM1.2 complete.** All 7 acceptance criteria are checked off and verified:

- 11/11 tests passing (\`pytest tests/\`), 9 new + 2 pre-existing hermetic canaries
- \`ruff check\` clean on both new test files
- \`bpsai-pair arch check --strict\` clean project-wide
- \`bpsai-pair task update DM1.2 --status done\` passed the strict AC gate

**Files added:** \`tests/test_evidence_model.py\`, \`tests/test_probe_contract.py\` — locking the trust ordering, provenance row, \`unobservable()\`, and the probe never-raise contract (including \`sweep()\` isolation and \`blind_spots()\`).

Along the way I found \`state.md\`'s DM1.1 blocker (no GitHub remote) was stale — \`origin\` now points at \`fivedollarfridays/deadman\` and DM1.1 already shows \`done\` — so I updated Current Focus, the task table, and Blockers to reflect reality rather than leave the outdated note in place.

**Next:** wave-2 tasks DM1.3, DM1.4, DM1.8, DM1.9 are unblocked and ready to start.