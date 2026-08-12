DM2C.2 is done — \`plan-sprint-2-engage\` is complete.

## Acceptance criteria

- **\[x\] \`docs/PROOF.md\`, written from captures not memory** — the case study reads from \`tests/fixtures/real-morning-brief-fault.json\` and a new \`tests/fixtures/real-board-capture.json\` (\`GET /\` off the deployed service, captured this session at 05:42:43Z while the outage was still live, HTTP 200). \`tests/test_proof_doc.py\` asserts every duration and timestamp in the prose is findable in one of the two captures.
- **\[x\] Detection latency vs. seven days, and why it hid** — 30h of deliberate probe tolerance plus at most one 900s sweep, with the 1800s collector-silence deadline as the term that makes the claim mean anything, against 176.7h found by accident. The self-concealing section names the brief as its own alerting channel.
- **\[x\] \`docs/DEMO.md\` rewritten as a run sheet** — pre-flight (every command executed and corrected against this Mac), seven beats covering the live board's real FAULT, the collector, the wire, the scheduler's \`self:sweep\` evidence, the alarm mail, the live demo, the arithmetic. The unedited-single-take and visual-proof-of-GCP rules lead the document.
- **\[x\] Break-and-heal against a real surface** — new stage 1, \`scripts/demo_real_surface.py\`: a real probe over a real file, broken by the outage's own last log row, escalated (no shipped action fixes a hung cron job), healed by a real write and proved by a fresh observation. 8 tests pin it, including that it never imports the demo stubs.
- **\[x\] \`sample-outputs/\` regenerated and byte-enforced** — and it now actually runs outside pytest; see the defects below.
- **\[x\] Diagram shows the split** — topology band with each surface on the side of the wire it's read on, PNG re-rendered, panel membership asserted by test.
- **\[x\] README reproduces from a clean clone** — run verbatim in two fresh temp dirs: \`main\` from GitHub (573 passed) and this branch (609 passed), plus demo, sample regeneration and \`deadman-self-check\` in the fresh clone.
- **\[x\] Gates in order** — 609 passed, \`ruff check\` clean, \`ruff format --check\` 178 files, \`arch check --strict\` no violations.

## Two things verification turned up

1. \`python scripts/generate_samples.py\` **failed from a plain shell** — \`deadman.service\` fails closed at import without secrets that only \`conftest\` set, so the documented regeneration command worked only inside pytest. Fixed, pinned by a subprocess test with every \`DEADMAN_*\` stripped.
2. \`infra/scheduler.md\` still claimed its steps were "not yet executed" — DM2.6 executed them. Now records the verification plus a check anyone can run without \`gcloud\`.

## One thing I could not verify

WebSearch and WebFetch were not permitted in this session, so I could not re-read the Devpost rules page myself. The run sheet states both rules, names their provenance (judging weights verified from the Devpost page per \`plans/backlogs/DM2C-close.md\`; the two rules recorded in \`docs/SPRINT-BRIEF-DM1.md\`), and instructs re-reading the rules page immediately before recording. Worth doing before the take.

Two commits on \`engage/dm2c-close\`, branch green and ready to merge. After merging, redeploy — the live revision (\`86c3662\`) predates DM2C.1's \`reported_by\`/\`held_since\`, which the committed capture records honestly.