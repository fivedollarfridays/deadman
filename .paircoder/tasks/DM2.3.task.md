---
id: DM2.3
title: 'The collector: sweep where the surfaces actually are'
plan: plan-sprint-2-engage
status: done
sprint: '2'
depends_on:
- DM2.2
materialized_by: backlog_materializer
priority: P0
complexity: 35
complexity_scale: lane
type: feature
ac_verified: true
model: claude-sonnet-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: e7bffbd1bb2e3810abad6cbd40aea8fa9f1e61ec
  started_at: '2026-08-11T20:01:19.051698+00:00'
  completed_at: '2026-08-11T20:15:24.032176+00:00'
completed_at: '2026-08-11T20:13:52.295762+00:00'
---

# The collector: sweep where the surfaces actually are

Build the process that runs on Kevin's machines, sweeps the local surfaces, and ships a signed batch to the ingest endpoint. Which probes run is configuration, not code, because the whole point is that adding a surface on a new machine does not mean editing the collector. Store-and-forward is non-negotiable: an unreachable service must never cause evidence to be dropped, since a network blip would then look exactly like a healthy estate. Dry-run exists so the thing can be inspected before it is trusted with a real rail.

# Acceptance Criteria

- [x] `src/deadman/collector/config.py` reads which probes to run, and their arguments, from a config file rather than from code
  — `load_config`/`parse_config` read a JSON file into `ProbeSpec`s; `PROBE_TYPES`
  maps a type name to the real dataclass; `build_probes` constructs them, coercing
  string args to `Path` off the target dataclass's own field annotations, so a
  probe registered later needs no matching change here. `tests/test_collector_config.py`
  (22 tests), plus `tests/test_collector_example_config.py` proving
  `infra/collector/collector.example.json` actually parses and builds real probes.
- [x] A probe that raises is contained and the remaining surfaces' evidence still ships, matching the `run_probe` contract
  — the collector calls `deadman.probes.base.sweep()` directly rather than
  reimplementing isolation; `tests/test_collector_run.py::TestProbeIsolation::
  test_a_raising_probe_does_not_stop_the_others_from_shipping` (a raising probe's
  row arrives `UNOBSERVABLE`, its sibling's `HEALTHY` row still ships in the
  same batch).
- [x] An unreachable service writes the batch to a local spool and re-sends it on a later run, never dropping it
  — `tests/test_collector_run.py::TestStoreAndForward::test_an_unreachable_service_spools_rather_than_drops`,
  `test_a_non_200_response_also_spools_rather_than_drops` (a reachable-but-rejecting
  service is treated the same way — never dropped), and
  `test_a_later_successful_run_drains_the_spooled_batch` (drains before the new sweep,
  `drained == 1`, spool empty after).
- [x] The spool survives process restart, asserted by a test that reconstructs the collector from disk
  — `tests/test_collector_run.py::TestStoreAndForward::test_spool_survives_restart_via_a_reconstructed_collector`
  builds a second `Collector` with no reference to the one that spooled the batch;
  unit-level in `tests/test_collector_spool.py::TestSurvivesRestart` (fresh `Spool`
  instance over the same path, plus a round-trip-through-disk fidelity check).
- [x] `--dry-run` prints the batch it would ship and makes zero network calls, asserted under the hermetic socket block
  — `tests/test_collector_run.py::TestDryRun::test_dry_run_makes_zero_network_calls_under_the_real_transport`
  runs dry-run with the *real* `UrllibTransport` (not a mock) inside the suite's
  hermetic socket block from `conftest.py`; a pass means it never dialed out.
  `test_cli_dry_run_prints_json_to_stdout` proves the CLI actually prints it.
- [x] The collector signs its batch with the DM2.2 wire format and attaches its own collector id
  — `tests/test_collector_run.py::TestSigningAndWireFormat::test_the_shipped_batch_is_signed_and_carries_the_collector_id`
  verifies the body with `deadman.ingest.auth.check_signature` and decodes it with
  `deadman.ingest.wire.loads`, the exact functions the real ingest endpoint uses.
  Resends are freshly signed, not replayed:
  `test_the_resent_batch_is_freshly_signed_not_replayed_stale`.
- [x] `infra/launchd/com.deadman.collector.plist` installs on the Mac with one documented command in the README
  — plist validated with `plutil -lint` (real tool, real check); `infra/README.md`
  "Installing the collector on a Mac" documents the secret file, the config file, and
  the one `sed | launchctl load` command, which was executed by hand against the
  template during this task (substitution and `plutil -lint` both verified; `launchctl
  load` itself was not run, since installing a live recurring background job on this
  machine is outside what this session should do unattended).
- [x] A malformed config fails loudly at startup naming the offending key, rather than silently sweeping nothing
  — every `ConfigError` in `config.py` names the specific key or probe index;
  `tests/test_collector_config.py::TestParseConfig` (missing keys, bad types, unknown
  probe type, mismatched args) and `tests/test_collector_run.py::TestStartupFailures`
  (CLI exits non-zero with the key in stderr; a missing `DEADMAN_INGEST_SECRET` fails
  loudly too, naming the variable).
- [x] Gates: `pytest -n auto --dist=worksteal` green, `ruff check .` and `ruff format --check .` clean, `bpsai-pair arch check --strict` clean
  — 412/412 passed (up from 362); `ruff check .` and `ruff format --check .` both
  clean; `bpsai-pair arch check --strict` clean.