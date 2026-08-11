**DM1.10 complete** — all six acceptance criteria verified by the strict AC gate.

## What was built

\`src/deadman/correlate/\` — four modules on a deliberate seam:

| Module | Decides | On what |
|---|---|---|
| \`window.py\` | which faults are worth one question | \`read_at\` proximity — deterministic, and establishes *nothing* |
| \`engine.py\` | whether they share a cause | the diagnosis layer's existing grounded-citation contract |
| \`incident.py\` | what a correlation is as a type | \`basis\`, three statuses, two constructor invariants |
| \`report.py\` | what a human is told | inferred-not-traversed, both confidence numbers, unexplained surfaces |

## The design question it turned on

Co-occurrence is nearly worthless as evidence. Every probe in a sweep runs within milliseconds of every other, so two faults share a \`read_at\` whether or not they share a cause — and \`read_at\` is when *we looked*, not when the fault began. So **the window proposes and the cited evidence disposes**: candidacy contributes nothing to confidence, and membership in an incident is read off the citations, never off the window. A relationship requires quoted evidence from two or more *faulting* surfaces.

The test that keeps this from being a time-bucket is \`grounded-disk-only\` — a perfectly good grounded diagnosis over the same three co-occurring rows, which happens to be a diagnosis *about the disk*. Three broken things in one window, no correlation.

Blindness is refused as a leg twice, because the model chooses what it cites. I added one recording, \`grounded-blind-relay-tie\`: fully grounded, quotes the disk trend *and* the relay's own "cannot observe" — two surfaces, two citations, one tidy story, refused. A relay we could not reach cannot corroborate anything.

On the flagship cascade the incident lands at **0.4 from a claimed 0.7**, because the tie to the scheduler runs through a \`REPORTED\` row. Both numbers render, so the cap reads as a cap. What the incident doesn't explain (\`sms:relay\`) is a listed section rather than a discount — folding it into a smaller number would say we were less sure and never say of what.

## Verification

192/192 tests (up from 158), \`ruff check\` clean, \`arch check --strict\` clean. Per the DM1.6 lesson recorded in state.md, I didn't trust the green first run: **all ten guards were mutation-checked**, each inversion breaking a specific named test, with \`PYTHONDONTWRITEBYTECODE=\[REDACTED_ENV\] throughout to avoid the stale-\`.pyc\` trap.

That exercise found one real problem. The two "grounded but still uncorrelated" tests would also have passed if the evidence-id scheme drifted — an ungrounded answer yields \`UNCORRELATED\` too, so they'd prove only that a broken citation is rejected, which is another layer's test. \`test_diagnose.py\`'s id pin covers the disk and Metricool ids but not \`sms:relay\`'s. Both tests now assert the fixture is \`GROUNDED\` first.

## Not done, deliberately

Not wired into \`service.py\`, for the same reason DM1.6 wasn't: correlation needs a model client and that endpoint holds no credentials. DM1.12 is the call site that has both, and \`report.as_dict\` is already board-shaped. I've noted in state.md that this is the layer that visibly does something a graph-based monitor cannot, so it belongs in the demo take.

**DM1.7 (verification loop, P0) is now the only unblocked task left.** DM1.8 remains blocked on a human with \`gcloud\` access.