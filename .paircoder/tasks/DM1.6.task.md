---
id: DM1.6
title: Remediation registry and executor
plan: plan-sprint-1-engage
status: done
sprint: '1'
depends_on:
- DM1.5
materialized_by: backlog_materializer
priority: P0
complexity: 35
complexity_scale: lane
type: feature
model: claude-opus-5
base_branch: main
runtime:
  pre_task_sha:
    worktree: d5d5f6f891c076d76622cdbc55bb8b47a3fca14a
  started_at: '2026-08-11T02:01:10.273285+00:00'
  completed_at: '2026-08-11T02:15:46.208569+00:00'
completed_at: '2026-08-11T02:14:14.835649+00:00'
ac_verified: true
---

# Remediation registry and executor

The Taskmaster requirement. Selection is a function of the diagnosis rather than the fault, because re-queueing a post that failed on an expired token fails identically, and re-queueing one rejected on policy is worse than doing nothing. Actions themselves are deterministic code, never model output.

# Acceptance Criteria

- [x] Action selection keys on the diagnosis, not the fault class —
      `test_remediate_selection.py::test_one_fault_class_two_diagnoses_two_different_actions`
      holds `bundle-metricool-publish-failure` constant (one fault: a scheduled
      post absent at the destination) and varies only which evidence the model
      cited, yielding `retry-now` vs `refresh-credential`.
      `test_the_hypothesis_prose_cannot_talk_the_executor_into_a_retry` proves
      the other direction: a grounded diagnosis whose prose says "retry ... and
      re-queue the post right away" still selects no retry.
- [x] An expired-credential diagnosis does not select a retry action —
      `test_an_expired_credential_diagnosis_never_selects_a_retry`, plus
      `test_a_diagnosis_citing_both_causes_still_refuses_the_retry` for the
      harder case where a 503 is cited alongside the expiry and precedence
      still refuses (`cause.PRECEDENCE`).
- [x] A transient 5xx diagnosis does select an immediate retry —
      `test_a_transient_5xx_diagnosis_selects_an_immediate_retry` and
      `test_remediate_cause.py::test_a_5xx_is_a_transient_upstream_cause`.
      429 is deliberately excluded and escalates
      (`test_a_rate_limit_is_deliberately_not_classified_transient`).
- [x] Every action is deterministic code; no action body is generated at
      runtime — `Registry.register` calls `_reject_generated_body`, which
      refuses any callable with no source file behind it.
      `test_a_runtime_generated_action_body_cannot_be_registered` registers an
      `exec`-built function and asserts it raises;
      `test_every_shipped_action_body_lives_in_this_package` resolves every
      shipped action back to a file in `src/deadman/remediate/`. The reach of
      the check is stated plainly in `registry.py` — it stops the obvious route
      and is not a sandbox.
- [x] A diagnosis with no matching action escalates rather than guessing — six
      refusal branches in `Executor._refusal`, every one with a test:
      `test_an_ungrounded_diagnosis_escalates_and_never_acts` and
      `test_an_unavailable_diagnosis_escalates_and_never_acts` (the
      `is_actionable` gate), `test_cited_evidence_that_was_not_supplied_escalates`,
      `test_a_fault_no_rule_recognises_escalates_rather_than_defaulting_to_retry`
      (cause `UNKNOWN`),
      `test_a_policy_rejection_escalates_because_no_code_can_fix_it` (cause
      recognised, no action registered on purpose),
      `test_a_diagnosis_resting_on_a_schedulers_word_cannot_trigger_an_action`
      (confidence floor), and
      `test_an_action_without_its_capability_wired_escalates`.
- [x] Dry-run mode executes selection and reports the plan without side effects
      — `test_dry_run_selects_and_reports_without_touching_anything`,
      `test_dry_run_is_the_default` (fail-closed: a wet run must be asked for),
      `test_the_plan_is_identical_whether_or_not_it_is_executed`, and
      `test_planning_alone_never_executes`.
- [x] `ruff check` clean on touched files — `ruff check .` clean repo-wide;
      `pytest tests/` 157/157 (up from 117); `bpsai-pair arch check --strict`
      clean.

# Verification

Every guard above was mutation-checked: it was inverted in the implementation
and the suite re-run to confirm a named test actually fails. Reordering
`PRECEDENCE`, classifying 429 as transient, classifying healthy/blind rows,
ignoring `dry_run`, dropping the `is_actionable` gate, dropping the `UNKNOWN`
branch, dropping the confidence floor, dropping the capability check, and
skipping `_reject_generated_body` each broke a specific test rather than
passing silently.

Note for anyone repeating this: a pure-reorder mutation leaves the file the
same size, and if the edit and the restore land within the same second Python
reuses the stale `.pyc`. One apparently-clean run here was still executing
mutated bytecode. Purge `__pycache__` or set `PYTHONDONTWRITEBYTECODE=1`.