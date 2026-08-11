**DM1.5 done.** All 7 AC verified by the strict gate; committed as \`384be74\` + \`6a4408b\`.

## The design question this turned on

"The model may not assert a fact it wasn't given" is hard to enforce when the output is prose. The answer here is to stop treating a response as one thing:

- **\`citations\`** — \`{evidence_id, quote}\`, where the quote must appear **verbatim** in the *specific* evidence it names. Checked per-evidence, not against the whole pile — attributing the scheduler's 500 to the disk read is a causal claim, and letting it through because the string exists *somewhere* would smuggle the interesting part of the reasoning past the check.
- **\`hypothesis\`** — free prose, allowed to be new text. That's the reason a model is here rather than a rule engine.

**Rejection is all-or-nothing.** One invented fact among four good citations discards the whole answer — the hypothesis was reasoned from it along with the rest, so salvaging the survivors leaves a conclusion on a premise that was thrown out. The planted-fabrication recording is built that way deliberately (one real citation, one invented); a wholly fabricated response is the easy case.

**Three statuses, mirroring \`Observation\`.** \`UNGROUNDED\` ("the model said something false") and \`UNAVAILABLE\` ("we couldn't read what it said") are never collapsed. The engine never raises — same contract as \`run_probe\`, one layer up.

Four evasion routes fail closed, including one worth naming: an evidence id smuggled into the *prose* while every citation is legitimate. A citations-array-only check passes that.

## Beyond the AC, and why

Confidence is **capped, not accepted** — the weakest cited evidence sets the ceiling off \`Method\`'s existing trust ordering. The flagship recording claims 0.7 leaning partly on a scheduler report and lands at 0.4, with the model's own number kept alongside since the gap is itself a signal. Without this, "confidence" is a number the model made up.

## What I did not solve, stated rather than papered over

Arbitrary unsupported prose *inside* the hypothesis can't be detected deterministically. The defence is structural, not detective: the hypothesis is never consumed as fact, carries capped confidence, and DM1.6 selects deterministic code off the diagnosis. A fabricated sentence is visible to a human and inert to the machine. That boundary is written into \`grounding.py\` and \`docs/ARCHITECTURE.md\` rather than left implied.

## One thing needs a human

The ADK call shape in \`gemini.py\` is the only unexercised path — no \`google-adk\` and no GCP credentials here, same constraint as the DM1.8 blocker. It's written to the documented interface and flagged with a \`.. warning::\` naming the exact smoke test. **Contest eligibility requires a real Gemini call at least once**, so I've put it alongside the DM1.8 deploy in What's Next — one sitting with GCP access clears both. Everything downstream of the model is model-agnostic and fully covered offline, so that gap blocks nothing but the smoke test itself.

Gates: \`pytest\` 117/117 (up from 61), \`ruff check .\` clean, \`arch check --strict\` clean. DM1.6 and DM1.10 are now unblocked.