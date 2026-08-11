---
id: DM2.2
title: Authenticated ingest, and what a reported observation means
plan: plan-sprint-2-engage
status: done
sprint: '2'
depends_on:
- DM2.1
materialized_by: backlog_materializer
priority: P0
complexity: 35
complexity_scale: lane
type: feature
ac_verified: null
model: claude-opus-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: 8241194dc6bb7d6c6b29821d9779a2e19eabb1ea
  started_at: '2026-08-11T19:25:52.309852+00:00'
completed_at: '2026-08-11T19:45:21.395689+00:00'
---

# Authenticated ingest, and what a reported observation means

Add `POST /evidence` so a collector can ship a signed batch to the service, and encode the provenance rule that makes remote evidence honest. The interesting part is not the HTTP: it is that a report of a local reading is a weaker claim than the reading, and the method must not be upgraded on arrival. Replay safety matters because a collector that cannot reach the service will re-send, so a duplicated batch must not double the history and manufacture a false trend. Auth fails closed: a missing shared secret refuses to start rather than quietly accepting unsigned batches.

# Acceptance Criteria

- [x] `POST /evidence` accepts a correctly signed batch and stores every row through the DM2.1 `EvidenceStore`
  — `IngestEndpoint` writes through `EvidenceStore.append`;
  `test_ingest_endpoint.py::TestAcceptedBatch::test_a_correctly_signed_batch_stores_every_row`
  (two surfaces, both readable back), and at the WSGI layer
  `test_service.py::TestIngestRouting::test_a_signed_batch_posted_to_evidence_is_stored`.
- [x] An unsigned or wrongly signed batch is rejected with an auth failure and stores nothing
  — `TestRejection::test_an_unsigned_batch_is_refused_and_stores_nothing`,
  `..._a_wrongly_signed_batch_...`, `..._a_tampered_row_invalidates_the_signature`.
  All three assert `store.latest_per_surface() == {}`. Mutation: removing the
  signature check breaks 3 tests.
- [x] A batch whose signature timestamp falls outside the freshness window is rejected as stale
  — `TestRejection::test_a_batch_signed_outside_the_freshness_window_is_stale`
  (asserts `"stale"` in the error) and `..._a_stale_batch_is_refused_even_though_its_signature_is_valid`
  (future skew). Unit-level in `test_ingest_auth.py::TestFreshness`, incl. a
  test that the window is bounded in both directions.
- [x] Every stored row carries `collector_id` and an arrival time as fields distinct from `read_at`
  — `detail['collector_id']` and `detail['received_at']`;
  `test_ingest_arrival.py::test_arrival_time_is_a_distinct_field_from_read_at`
  and `test_ingest_endpoint.py::test_stored_rows_carry_the_collector_and_an_arrival_time`,
  which asserts `read_at` is still the collector's.
- [x] The method is never upgraded on arrival, asserted by a test that fails if the arrival mapping is made the identity function
  — `test_ingest_arrival.py::test_the_arrival_mapping_is_not_the_identity_function`.
  Mutation-verified: `return ON_ARRIVAL[claimed]` → `return claimed` fails 4
  tests. Separately, dropping the `on_arrival` call at the endpoint (which
  leaves every arrival unit test green) fails
  `test_the_method_is_downgraded_on_the_row_that_is_actually_stored`.
- [x] A replayed identical batch is idempotent: history length is unchanged, asserted by a test
  — `TestReplay::test_a_replayed_identical_batch_does_not_grow_the_history`
  (`len(history) == before == 1`, `duplicates == 2`), plus
  `..._even_when_arrival_time_has_moved_on` and a counter-test that a genuinely
  new reading is still recorded, so idempotency cannot become deafness.
- [x] The shared secret is read from the environment, never committed, and a missing secret fails closed at startup rather than accepting unsigned batches
  — `auth.secret_from_env` raises `IngestNotConfigured`; `service.py` calls it
  at module scope. `test_ingest_startup.py` proves the refusal in a real
  subprocess with the variable stripped, including that `app` does not exist
  afterwards, and `TestNothingSecretIsCommitted` scans the repo for any
  committed assignment whose value is not a shell/Secret-Manager reference.
- [x] `src/deadman/ingest/wire.py` round trips `Evidence` without losing provenance, including `Method` and `detail`
  — `test_ingest_wire.py::TestRoundTrip`: whole-batch equality, `Method` +
  `detail` + `provenance_row()` verbatim, and every `Method` member round
  tripped. 8 further tests cover malformed input.
- [x] A malformed or oversized body is rejected as a 4xx rather than raising a 500
  — `TestMalformedAndOversized`: 400 for non-JSON, missing fields and a
  non-integer `Content-Length`; 413 for an oversized declared length *and* for
  a body longer than a lying `Content-Length`; 4xx for an absent body or
  missing `wsgi.input`.
- [x] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean
  — 342 passed (up from 265); `ruff check` clean; `ruff format --check` clean
  (127 files); `arch check --strict` clean.