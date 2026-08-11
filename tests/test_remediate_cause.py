"""Cause classification: what the cited evidence actually says.

Everything read here was written by probe code. The model's only contribution
upstream of this is *which* evidence rows are in scope, so these tests build
evidence directly rather than going through a recording — the classifier never
sees a model at all.
"""

from __future__ import annotations

from datetime import datetime, timezone

from deadman.evidence.model import Evidence, Method, Observation
from deadman.remediate.cause import PRECEDENCE, Cause, causes_in, classify

READ_AT = datetime(2026, 8, 11, 4, 0, tzinfo=timezone.utc)


def ev(observation: Observation = Observation.FAULT, summary: str = "something broke", **detail):
    return Evidence(
        surface="metricool:api/publish",
        observation=observation,
        method=Method.DESTINATION_API,
        summary=summary,
        source="POST /v1/publish",
        read_at=READ_AT,
        detail=detail,
    )


# --- the two the acceptance criteria name directly -----------------------


def test_a_5xx_is_a_transient_upstream_cause():
    assert classify([ev(http_status=503, error_code="upstream_unavailable")]) is (
        Cause.TRANSIENT_UPSTREAM
    )


def test_an_expired_token_is_a_credential_cause_not_a_transient_one():
    assert classify([ev(http_status=401, error_code="token_expired")]) is (Cause.EXPIRED_CREDENTIAL)


# --- the closed set of signals -------------------------------------------


def test_a_policy_refusal_is_its_own_cause():
    assert classify([ev(http_status=403, error_code="policy_violation")]) is Cause.POLICY_REJECTION


def test_a_disconnected_channel_is_its_own_cause():
    assert classify([ev(http_status=403, error_code="channel_disconnected")]) is (
        Cause.CHANNEL_DISCONNECTED
    )


def test_a_disk_trend_is_a_resource_cause():
    disk = Evidence(
        surface="host:mac/disk",
        observation=Observation.FAULT,
        method=Method.LOCAL_ARTIFACT,
        summary="free space projected to hit the 10GB floor in 2.1 days",
        source="shutil.disk_usage('/')",
        read_at=READ_AT,
        detail={"free_gb": 12.4, "slope_gb_per_day": -20.0, "runway_days": 2.1},
    )
    assert classify([disk]) is Cause.RESOURCE_EXHAUSTION


def test_enospc_in_an_error_body_is_a_resource_cause():
    assert classify([ev(body="OSError [Errno 28] no space left on device")]) is (
        Cause.RESOURCE_EXHAUSTION
    )


# --- fail closed rather than guess ---------------------------------------


def test_an_unrecognised_failure_is_unknown_not_transient():
    """The dangerous default is 'probably transient, just retry'. An error
    nobody wrote a rule for is UNKNOWN, and UNKNOWN escalates."""
    assert classify([ev(http_status=418, error_code="teapot")]) is Cause.UNKNOWN


def test_a_rate_limit_is_deliberately_not_classified_transient():
    """429 means slow down. Reading it as a transient 5xx would select an
    immediate retry, which is the one response guaranteed to make it worse.
    Until a backoff action exists it escalates."""
    assert classify([ev(http_status=429, error_code="rate_limited")]) is Cause.UNKNOWN


def test_a_healthy_read_contributes_no_cause():
    """There is nothing to remediate on a surface that is fine, however
    suggestive its detail looks."""
    healthy = ev(
        observation=Observation.HEALTHY,
        summary="disk fine",
        http_status=503,
        runway_days=90.0,
    )
    assert causes_in(healthy) == set()
    assert classify([healthy]) is Cause.UNKNOWN


def test_a_blind_read_contributes_no_cause():
    """UNOBSERVABLE is a fact about us, not the surface. Acting on it would be
    acting on an absence of evidence."""
    blind = ev(observation=Observation.UNOBSERVABLE, summary="cannot observe", http_status=503)
    assert causes_in(blind) == set()


# --- precedence ----------------------------------------------------------


def test_a_credential_cause_outranks_a_transient_one():
    """Both are true at once. Retrying while the token is dead fails
    identically, so the blocking cause wins."""
    rows = [
        ev(http_status=503, error_code="upstream_unavailable"),
        ev(http_status=401, error_code="token_expired"),
    ]
    assert classify(rows) is Cause.EXPIRED_CREDENTIAL
    assert classify(list(reversed(rows))) is Cause.EXPIRED_CREDENTIAL, "order must not matter"


def test_a_policy_refusal_outranks_everything_actionable():
    rows = [
        ev(http_status=503),
        ev(http_status=401, error_code="token_expired"),
        ev(http_status=403, error_code="policy_violation"),
    ]
    assert classify(rows) is Cause.POLICY_REJECTION


def test_precedence_is_total_and_ends_in_unknown():
    """A cause missing from the ordering would sort arbitrarily against the
    others, which is how a retry sneaks ahead of a credential failure."""
    assert set(PRECEDENCE) == set(Cause)
    assert PRECEDENCE[-1] is Cause.UNKNOWN
    assert PRECEDENCE.index(Cause.POLICY_REJECTION) < PRECEDENCE.index(Cause.TRANSIENT_UPSTREAM)


def test_no_evidence_at_all_is_unknown():
    assert classify([]) is Cause.UNKNOWN
