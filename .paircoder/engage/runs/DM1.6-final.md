**DM1.6 complete** — \`bpsai-pair task update DM1.6 --status done\` passed the strict AC gate; all seven criteria checked with the specific test satisfying each.

## The design question this turned on

The diagnosis is a hypothesis in *prose*. So what does "selection keys on the diagnosis" mean without the model's words becoming the key? The decision splits three ways:

| | Who decides | On what |
|---|---|---|
| Which evidence is causal | **the model** | messy heterogeneous failure material |
| What that evidence means | \`remediate/cause.py\` | status/error codes and probe-authored summaries — rules written in advance, output from a closed enum |
| What to do about it | \`remediate/registry.py\` | a table from \`Cause\` to a function that existed before the run |

No string a model produced is ever a key, an argument, or a body.

## What makes the central AC real

\`tests/recorded/bundle-metricool-publish-failure.json\` holds **one fault class** — a scheduled post absent at the destination — with four candidate causes beside it. Five recordings cite different rows, so the fault stays constant and only the diagnosis varies: \`retry-now\` vs \`refresh-credential\` vs escalate.

\`grounded-expired-credential\` is deliberately adversarial: fully grounded, every cited fact checks out, and its prose says in plain English to *"retry … and re-queue the post right away."* No retry is selected — selection reads the cited evidence, not the sentence.

Beyond the literal ACs: precedence (a diagnosis citing a 503 *and* a lapsed token still refuses the retry), six refusal branches each tested, and every action's confidence floor sits above \`Method.REPORTED\`'s 0.4 ceiling — so the cap earned in DM1.5 now does real work rather than being a number in a report.

## Verification

Gates: **158/158** (up from 117), \`ruff check .\` clean, \`arch check --strict\` clean.

Every guard was mutation-checked rather than trusted from the green first run — the suite passed 40/40 on first execution, which is exactly when a test file deserves suspicion. Inverting each guard in turn (precedence order, 429-as-transient, classifying healthy/blind rows, ignoring \`dry_run\`, dropping the grounding gate, the \`UNKNOWN\` branch, the confidence floor, the capability check, the generated-body guard) broke a specific named test each time.

That exercise caught a trap worth recording: a pure-reorder mutation leaves the file the same size, and when edit and restore land in the same second Python reuses the stale \`.pyc\`. One apparently-clean run was still executing mutated bytecode — I only noticed because a test failed that had passed minutes earlier.

**Two things I did not do, deliberately:**
- **Not wired into \`service.py\`.** DM1.7 is the natural call site; an executor on the board with nothing re-observing would report actions taken with no check on whether they helped — the heartbeat problem this project argues against. \`Capabilities\` is the injection point: all optional, all defaulting to absent, and an unwired capability escalates.
- **429 is not classified transient.** Reading a rate limit as a 5xx selects an immediate retry, the one response guaranteed to make it worse. It escalates until a backoff action exists.