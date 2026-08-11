All gates green, task marked \`done\`, and \`state.md\` updated.

## Summary

DM2.5 is complete. The collector is now wired to real infrastructure:

- **\`DiskProbe\`** gained a \`host\` field so the same probe produces distinct, stable surface ids per machine (\`host:mac/disk\`, \`host:rig/disk\`) instead of colliding on \`/\`.
- **\`infra/collector/collector-rig.example.json\`** (new) demonstrates that the second disk surface needed zero new probe code — just a config edit reusing \`disk\`.
- **\`infra/collector/collectors.example.json\`** now declares both \`kevin-mac\` and \`kevin-rig\`.
- **Missing paths** now surface explicitly as \`detail\["path"\]\` on \`UNOBSERVABLE\` (both \`DiskProbe\` and \`MorningBriefProbe\`), never \`FAULT\`.
- **\`tests/fixtures/real-morning-brief-fault.json\`** is a real capture — \`MorningBriefProbe\` run this session against Kevin's actual \`~/ops/data/brief-send-log.jsonl\`: \`FAULT\`, no brief sent in 176.7h — committed for DM2.9's case study, pinned by a test so a future fix silently going stale as "evidence" would fail loudly.
- **\`docs/surfaces.md\`** (new) documents each real surface's path, cadence, and blindness meaning.
- A round-trip test proves paths come from config, never a hardcoded literal.

Gates: 494/494 tests passing (up from 485), \`ruff check\`/\`ruff format --check\` clean, \`bpsai-pair arch check --strict\` clean. Next up per \`state.md\`: DM2.6 (scheduled sweeps), unblocked by DM2.4.