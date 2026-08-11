---
id: DM1.4
title: Metricool probe and destination-verification spike
plan: plan-sprint-1-engage
status: done
sprint: '1'
depends_on:
- DM1.1
materialized_by: backlog_materializer
priority: P1
complexity: 35
complexity_scale: lane
type: feature
model: claude-opus-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: e9071d2c59646b3ebaa38159ee6790a5d1abc3be
  started_at: '2026-08-11T01:17:36.155543+00:00'
  completed_at: '2026-08-11T01:33:50.285324+00:00'
completed_at: '2026-08-11T01:33:20.425581+00:00'
ac_verified: true
---

# Metricool probe and destination-verification spike

The surface with a real incident behind it: a scheduled post reported published and never appeared, uncaught. Open with a spike establishing whether the destination platform is readable at all, because Meta approval appears unavailable and that decides the evidence tier this probe can honestly claim.

# Acceptance Criteria

- [x] `docs/metricool-verification.md` records whether the platform is readable via API, public permalink, or neither
  — Findings table plus per-platform detail, from live `curl` probes run
  2026-08-11: **Instagram neither** (permalink returns 200 for a real famous
  public post *and* 200 for a nonexistent shortcode, both carrying
  `"pageID":"httpErrorPage"`, identical under Chrome / `facebookexternalhit` /
  `Googlebot`; `instagram_oembed` returns the same 400 "Media Not Found" for
  the real post without an approved Meta app). **Facebook neither** (400 for
  every shape, including a real public page). **X public permalink readable**
  (200 vs 404, stable over two passes on 3 real + 3 fabricated ids and 10
  consecutive requests, with the post text in `og:description`). LinkedIn
  recorded as an untested candidate, not a finding. Exact commands are in the
  doc so the re-run before the demo is cheap.
- [x] The chosen verification path is expressed as a `Method` and the resulting trust tier is documented
  — "Decision" section: `Method.DESTINATION_PUBLIC`, **trust tier 3 of 5**,
  above `ACTIVE_CANARY`/`LOCAL_ARTIFACT`/`REPORTED` and below only
  `DESTINATION_API`, with why it is weaker than an authenticated read. The doc
  also records that `DESTINATION_API` is unavailable for every Metricool
  destination and that Metricool's own API would be `REPORTED`, tier 0. Encoded
  in `PLATFORM_VERIFICATION` (`src/deadman/probes/destinations.py:44`).
- [x] Scheduler-reported success alone never yields `HEALTHY`
  — Enforced three ways, each tested.
  `test_opaque_platform_is_unobservable_and_the_destination_is_never_fetched`:
  a reported-published Instagram post is `UNOBSERVABLE` and the permalink is
  not fetched at all (`reader.read_ids == []`), because the response cannot
  vary. `test_present_read_on_a_weak_method_cannot_yield_healthy`: a reader
  returning `PRESENT` on `Method.REPORTED` still cannot produce `HEALTHY` —
  the `trust(read.method) >= MIN_TRUST_FOR_HEALTHY` guard makes it structural,
  and the report says why. `test_an_empty_schedule_is_unobservable_not_healthy`
  and `test_unknown_platform_fails_closed_to_unobservable`: silence and
  unlisted platforms fail closed.
- [x] A post reported published but absent at the destination yields `FAULT` naming the post id
  — `test_post_reported_published_but_absent_is_fault_naming_the_post_id`
  asserts `FAULT`, `"roundtable-42" in evidence.summary`, and
  `detail["absent_post_ids"] == ["roundtable-42"]`; `_fault()` also records
  `absent_permalinks` so an operator can go straight to the thing that did not
  publish. `test_one_absent_post_among_confirmed_ones_still_yields_fault` and
  `test_a_confirmed_absence_outranks_an_unreadable_sibling` lock the
  precedence: one confirmed absence carries the batch, and a known fault is not
  downgraded by blindness on a sibling.
- [x] An unreachable destination yields `UNOBSERVABLE`, never `FAULT`
  — `test_unreachable_destination_is_unobservable_never_fault` (asserts
  `is not Observation.FAULT` explicitly, not merely the positive case),
  `test_a_raising_reader_is_unobservable_not_fault`,
  `test_a_raising_scheduler_is_contained_by_the_probe_contract` (via
  `run_probe`), and
  `test_permalink_reader_maps_rate_limits_and_server_errors_to_unreadable`
  (403/429/500/503 and a 0 from a transport that never connected). Also
  `test_a_post_inside_the_grace_period_is_not_yet_called_absent`: a post
  reported 36s ago is not called absent, because propagation delay is not a
  fault.
- [x] Tests cover published, missing, and unreachable with no live network calls
  — `tests/test_probe_metricool.py`, 20 tests, all passing; full suite 39/39
  (up from 19). Zero network: the scheduler and destination reader are both
  injected, `PermalinkReader` takes its transport as a parameter, the file
  contains no `allow_network` marker (`grep -c` → 0), and `conftest.py`'s
  autouse fixture blocks `socket.socket.connect` suite-wide — proven live in
  the same run by DM1.1's hermetic canaries.
- [x] `ruff check` clean on touched files
  — `ruff check .` → "All checks passed!" repo-wide (two E501s found and fixed
  during the run). `bpsai-pair arch check --strict` also clean: the first draft
  tripped "too many functions" (16 > 15) and a file-size warning, so the module
  was split at its real seam — `destinations.py` for what the platforms are and
  how to read them (spike knowledge, reusable by DM1.9's canary), `metricool.py`
  for how the probe reasons over a reported batch.