DM2C.1 is done. Summary:

**What changed:**
- New \`src/deadman/board.py\` — \`held_since\` (walks stored history back to the last state change, no division, falls back to the row's own \`read_at\` for empty/single-row history), \`reported_by\` (gated on \`detail\['received_at'\]\`, not just \`collector_id\`, so it never fires on the service's own derived liveness verdicts), \`history_for\` (bounded read via \`DEFAULT_HISTORY_LIMIT\`).
- \`src/deadman/service.py\` — \`store\` threads through \`build_board → make_app → build_app\`; every board row now carries \`held_since\`/\`held_seconds\` and (when applicable) \`reported_by\`. Helpers were split into \`board.py\` specifically to stay under the arch checker's per-file import/function caps — hit both simultaneously on the first pass.
- New tests: \`tests/test_board_memory.py\`, \`tests/test_board_dm1_contract.py\` (+ frozen \`tests/fixtures/dm1-board-sample.json\` from the DM1 merge commit). Updated \`tests/test_security_hardening.py\`: found and fixed a real collision the planning notes hadn't caught — adding \`reported_by\` breaks the old \`"mac-mini" not in str(published)\` assertion, so that test was narrowed to check \`detail\` specifically (the actual promise), paired with a new test proving both sides of the boundary.
- \`sample-outputs/board.json\` regenerated (additive fields only).

All 8 ACs checked off with evidence in the task file. Gates: 586/586 tests passing (up from 573), ruff clean, \`arch check --strict\` clean. \`bpsai-pair task update DM2C.1 --status done\` succeeded on the strict AC gate, and \`state.md\` is updated.

Changes are uncommitted per the git safety default — let me know if you'd like me to commit, or if you want to move on to DM2C.2 (integration gate + PROOF.md), which depends on this.