# Recorded model responses

The diagnosis tests never call a model. They replay what is in this directory,
so the suite stays hermetic (`tests/conftest.py` blocks outbound sockets for
every test that does not carry the `allow_network` marker, and nothing here
carries it).

- `bundle-*.json` — an evidence bundle, in the same shape
  `deadman.evidence.model.Evidence` serialises to. Recordings name the bundle
  they were produced against so the evidence ids in the response resolve.
- every other file — one model response, verbatim, plus the model name,
  temperature and prompt version it was produced under.

**Every recording carries a `captured` flag, and most of these are `false`.**
An authored recording is written against the response contract in
`deadman.diagnose.prompt`. It proves the parser handles a shape we invented,
which is worth something, but it is a weaker claim than it looks: we control
both sides, so it can never surprise us. They are deliberately realistic —
one is wrapped in a markdown fence because models do that, and several are
the specific ways a model goes wrong, which is exactly the material a live
capture is unlikely to hand you on demand.

`captured-disk-cascade.json` is the exception and is `captured: true`: a
verbatim response from live `gemini-3.5-flash`, produced by
`scripts/capture_recording.py`. See `docs/gemini-verification.md` for the
environment it needs. `tests/test_diagnose_captured.py` replays it, and when
that file and an authored fixture disagree, **the authored one is wrong.**

Refresh or add captures with:

```bash
python scripts/capture_recording.py bundle-disk-cascade captured-disk-cascade
```

Nothing downstream changes when a recording flips from authored to captured.
The engine only ever sees a string, which is why the envelope was designed
this way from the start.

## `bundle-metricool-publish-failure`

Added for DM1.6 and worth calling out, because it is built to make one specific
argument. Every row in it is the same fault — a scheduled post that never
reached the destination — and the rows differ only in *why*. The recordings
against it (`grounded-transient-5xx`, `grounded-expired-credential`,
`grounded-policy-rejection`, `grounded-mixed-cause`) hold the fault constant and
vary only what the model concluded was causal, which is how the remediation
tests show that selection keys on the diagnosis rather than the fault class.

`grounded-expired-credential` is deliberately adversarial: it is fully grounded
— every cited fact checks out — and its hypothesis says in plain English to
re-queue the post immediately. Selection reads the cited evidence, not the
sentence, so no retry is chosen. If that recording is ever replaced by a live
capture, keep a version whose prose recommends the wrong action; it is the only
test that proves model text cannot steer the executor.

## `bundle-disk-cascade` and the correlation recordings

The disk-fills-then-everything-dies case: one host, three surfaces, no lineage
graph between any of them. DM1.10 replays three responses against it, and the
argument is what *fails* to correlate rather than what succeeds.

- `grounded-disk-cascade` — the real thing. Cites the disk and the scheduler,
  ties them, and is capped from 0.7 to 0.4 because the tie runs through a
  `REPORTED` row.
- `grounded-disk-only` — the near miss. A perfectly good diagnosis over the
  same three co-occurring rows, which happens to be a diagnosis *about the
  disk*. Three broken things in one window and no relationship, which is the
  test that stops this task from being a time-bucket.
- `grounded-blind-relay-tie` — added for DM1.10 and the sharpest of the three.
  Fully grounded: it quotes the disk trend and it quotes the relay's own
  "cannot observe". Two surfaces, two citations, one tidy story — and no
  correlation, because a relay we could not reach cannot corroborate anything.
  If it is ever replaced by a live capture, keep a version that ties a fault to
  an `UNOBSERVABLE` row; it is the only test that proves blindness cannot
  become a leg.

`test_diagnose.py::test_recorded_evidence_ids_match_the_derived_scheme` asserts
the ids inside these responses still match what
`deadman.diagnose.schema.evidence_id` derives. If the id scheme ever changes,
these recordings fail loudly instead of silently citing nothing.
