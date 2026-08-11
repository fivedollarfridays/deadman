---
id: DM1.5
title: Diagnosis layer on Gemini via ADK
plan: plan-sprint-1-engage
status: done
sprint: '1'
depends_on:
- DM1.1
- DM1.2
materialized_by: backlog_materializer
priority: P0
complexity: 40
complexity_scale: lane
type: feature
model: claude-opus-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: f78187f15ce847856380865b96923a83dd8d2822
  started_at: '2026-08-11T01:45:57.446759+00:00'
  completed_at: '2026-08-11T02:01:06.017123+00:00'
completed_at: '2026-08-11T02:00:09.446525+00:00'
ac_verified: true
---

# Diagnosis layer on Gemini via ADK

Where the model earns its place. Detection is deterministic; diagnosis is inferential. This layer reads heterogeneous unstructured failure evidence and forms a causal hypothesis, which is the thing rule engines cannot do and the reason this is an agent rather than a cron job.

# Acceptance Criteria

- [x] Consumes unstructured `Evidence.detail` and emits a typed `Diagnosis`
  — `grounding.corpus_for()` renders every `detail` key *and* value into the
  quotable corpus and `prompt.render_evidence()` puts the raw detail in front
  of the model unsummarised. `test_diagnose.py::test_unstructured_detail_is_
  what_the_diagnosis_is_built_from` asserts a citation lands inside a worker
  log line and a computed slope; `test_diagnose_grounding.py::test_corpus_
  includes_unstructured_detail_values` and `::..._detail_keys_not_only_values`
  cover the corpus directly.
- [x] `Diagnosis` carries hypothesis, confidence, and the evidence ids it rests on
  — `schema.Diagnosis`. `test_the_diagnosis_rests_on_the_evidence_ids_it_cited`
  asserts the ids are exactly the cited ones and deduplicated;
  `test_the_blind_surface_is_not_claimed_as_support` asserts an uncited blind
  surface never appears among them. Confidence is the *capped* number
  (`test_confidence_is_capped_by_the_weakest_cited_evidence`), with the model's
  own claim kept alongside it in `claimed_confidence`.
- [x] A test plants a fabricated claim in the model response and asserts it is rejected
  — `tests/recorded/fabricated-token-claim.json` plants
  `"oauth token expired at 2026-08-01T00:00:00Z"` alongside one *legitimate*
  citation, because a wholly fabricated response is the easy case and a
  mostly-true one is not. `test_a_fabricated_claim_is_rejected` asserts
  `UNGROUNDED`, zero confidence and the reason naming the invented quote;
  `test_one_fabrication_discards_the_whole_answer` asserts the surviving good
  citations are discarded too; `test_a_rejected_hypothesis_is_still_shown_to_
  the_human` asserts the text is retained for review.
- [x] The model is never permitted to assert a fact absent from the supplied evidence
  — `grounding.reject_reason()` requires every cited fact to appear verbatim
  (case/whitespace-normalised only) in the *specific* evidence it is
  attributed to. Four evasion routes are tested and all fail closed: a
  fabricated quote; a quote lifted from a *sibling* piece of evidence
  (`test_quote_from_a_different_piece_of_evidence_is_rejected`); a
  hallucinated surface (`test_a_hallucinated_surface_is_rejected`); and an
  evidence id smuggled into the prose while every citation is legitimate
  (`test_an_evidence_id_smuggled_into_the_prose_is_rejected`). A hypothesis
  with no citations at all is rejected too. The boundary of what this can
  enforce is stated explicitly in `grounding.py` ("Where the enforcement
  ends") and in `docs/ARCHITECTURE.md` rather than overclaimed.
- [x] Tests run offline against recorded responses with no live API calls
  — 8 recordings in `tests/recorded/`, replayed via `tests/recordings.py`. No
  test in either file carries the `allow_network` marker, so `conftest.py`'s
  suite-wide socket block is in force; `test_no_diagnosis_test_opts_out_of_
  the_hermetic_fixture` asserts that at collection time rather than trusting
  it. `test_the_engine_pulls_in_no_model_sdk` asserts importing the layer
  drags in no `google.adk`/`google.genai`, and the SDK is imported inside
  `GeminiClient.__post_init__`, never at module scope. The `gemini` extra is
  deliberately kept out of `[dev]` so CI runs with no SDK present at all.
- [x] Model, temperature, and prompt version are recorded on every diagnosis
  — fields on `Diagnosis`, populated on all three statuses.
  `test_provenance_rides_on_rejected_and_unavailable_diagnoses_too`
  parametrises over grounded/ungrounded/unreadable/uncited, and
  `test_provenance_survives_the_model_being_unreachable` covers the case where
  the model never answered. `PROMPT_VERSION` is made honest by
  `test_editing_the_prompt_without_bumping_its_version_fails_this_test`, which
  pins `prompt_fingerprint()` so the constant cannot drift from the text it
  names.
- [x] `ruff check` clean on touched files
  — `ruff check .` clean repo-wide. Also `pytest tests/` 117/117 (up from 61)
  and `bpsai-pair arch check --strict` clean.