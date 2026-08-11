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

**These responses are authored against the response contract in
`deadman.diagnose.prompt`, not captured from a live Gemini call.** No
credentials exist in this environment (see the DM1.8 blocker in
`.paircoder/context/state.md` for the same constraint on GCP). They are
deliberately realistic — one is wrapped in a markdown fence because models do
that, and several are the specific ways a model goes wrong. Replace them with
real captures once a live smoke test has run; the loader and the engine will
not need to change, because the recording envelope is what a capture would
write.

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

`test_diagnose.py::test_recorded_evidence_ids_match_the_derived_scheme` asserts
the ids inside these responses still match what
`deadman.diagnose.schema.evidence_id` derives. If the id scheme ever changes,
these recordings fail loudly instead of silently citing nothing.
