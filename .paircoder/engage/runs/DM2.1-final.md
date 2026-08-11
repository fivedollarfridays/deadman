**DM2.1 is done.** \`bpsai-pair task update DM2.1 --status done\` reported "✓ All acceptance criteria verified", and state.md is updated.

## What landed

\`src/deadman/store/\` — Protocol in \`base.py\`, two backends behind it:

| Method | Contract |
|---|---|
| \`append\` | Idempotent for an identical row |
| \`latest(surface)\` | Newest by \`read_at\`; \`UNOBSERVABLE\` when nothing stored |
| \`latest_per_surface()\` | Only surfaces that have actually reported |
| \`history(surface, limit)\` | Newest \`limit\` rows, oldest first |

Three decisions worth flagging, since this seam feeds four downstream tasks:

**Absence returns evidence, not \`None\`.** \`latest()\` on an unreported surface returns \`unobservable(...)\`. \`None\` would push the judgement onto every caller, and one caller writing \`if not evidence\` reinstates the false green.

**\`history()\` is in the Protocol now, ahead of DM2.8.** Discovering in DM2.8 that held-duration needs a read the Protocol lacks would mean reopening the contract with three consumers already on it. It's contract-tested, so it isn't dead surface.

**Replay safety fell out of content-addressed identity.** \`row_id()\` hashes the encoded row, so a re-sent spool stores once and Firestore writes with \`set\` rather than racing a read-modify-write — DM2.2's idempotency AC gets this for free. Rows differing only in \`read_at\` stay distinct, which is what DM2.8 needs.

## Verification

The Firestore backend is contract-tested, not just written: it accepts an injected client, and \`tests/firestore_double.py\` reproduces the narrow API slice it calls. That double caught a real bug — surface \`host:mac/disk\` contains a \`/\`, which Firestore rejects in a document id, so the key needed percent-encoding.

Six mutations, each caught by a named test: unencoded surface key, ascending Firestore ordering, memory ordered by arrival, absence synthesised as healthy, identity by surface alone, dedup removed. A seventh check confirmed the AST seam guard fires on an injected module-scope \`from google.cloud import firestore\` — that's the half of the zero-dependency promise that has to hold on machines where the SDK *is* installed.

Gates: 265 passed (236 before, 29 new), \`ruff check\` clean, \`ruff format --check\` clean, \`arch check --strict\` clean. \`import deadman.store\` succeeds with no \`google*\` package present.

## One item for wave 2

The Dockerfile still installs \`.\` with no extras. Correct today — nothing constructs a \`FirestoreEvidenceStore\` yet — but whichever of DM2.2/DM2.6 first wires it into the deployed service must switch to \`.\[firestore\]\`, or the service fails closed at startup on the deploy rather than in CI. It's recorded in the task file's handoff section and in state.md's What's Next.

Nothing is committed — the working tree holds the new files plus the modified \`pyproject.toml\` and \`state.md\`.