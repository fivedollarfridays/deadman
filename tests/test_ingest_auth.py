"""Ingest authentication: the signature, the freshness window, the secret.

Three properties are being pinned here, and each one is a way the endpoint
could look secure and not be.

1. The MAC covers the *raw bytes received*, so nothing inside the payload —
   including ``signed_at`` — can be edited by whoever captured it.
2. The freshness window is checked against the signed timestamp, so a captured
   body stops being useful after a bounded time.
3. The secret comes from the environment and its absence is a refusal, not a
   default. A monitor that accepted unsigned batches because nobody set a
   variable would be worse than no monitor: it would report an estate it was
   being told about by anyone who could reach the URL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from deadman.ingest.auth import (
    FRESHNESS_SECONDS,
    SECRET_ENV,
    AuthError,
    IngestNotConfigured,
    secret_from_env,
    sign,
    verify,
)

SECRET = b"correct-horse-battery-staple"
NOW = datetime(2026, 8, 11, 7, 0, tzinfo=timezone.utc)
BODY = b'{"collector_id":"mac-studio","rows":[],"signed_at":"2026-08-11T07:00:00+00:00"}'


class TestSignature:
    def test_a_body_signed_with_the_secret_verifies(self):
        verify(BODY, sign(BODY, SECRET), SECRET, signed_at=NOW, now=NOW)

    def test_a_body_signed_with_a_different_secret_is_refused(self):
        with pytest.raises(AuthError):
            verify(BODY, sign(BODY, b"guessed"), SECRET, signed_at=NOW, now=NOW)

    def test_a_tampered_body_is_refused(self):
        signature = sign(BODY, SECRET)

        with pytest.raises(AuthError):
            verify(BODY.replace(b"mac-studio", b"rig-linux"), signature, SECRET, NOW, NOW)

    def test_a_missing_signature_is_refused(self):
        """Absent is not a special case that skips the check."""
        for missing in (None, "", "   "):
            with pytest.raises(AuthError):
                verify(BODY, missing, SECRET, signed_at=NOW, now=NOW)

    def test_a_signature_that_is_not_hex_is_refused_rather_than_raising(self):
        with pytest.raises(AuthError):
            verify(BODY, "not-a-hex-digest", SECRET, signed_at=NOW, now=NOW)


class TestFreshness:
    def test_a_batch_signed_now_is_fresh(self):
        verify(BODY, sign(BODY, SECRET), SECRET, signed_at=NOW, now=NOW)

    def test_a_batch_signed_before_the_window_is_stale(self):
        old = NOW - timedelta(seconds=FRESHNESS_SECONDS + 1)

        with pytest.raises(AuthError) as caught:
            verify(BODY, sign(BODY, SECRET), SECRET, signed_at=old, now=NOW)

        assert "stale" in str(caught.value)

    def test_a_batch_signed_inside_the_window_is_accepted(self):
        recent = NOW - timedelta(seconds=FRESHNESS_SECONDS - 1)

        verify(BODY, sign(BODY, SECRET), SECRET, signed_at=recent, now=NOW)

    def test_a_batch_signed_far_in_the_future_is_refused(self):
        """Clock skew is bounded in both directions.

        A one-sided window lets a captured body be replayed indefinitely by
        dating it forward, which would make the freshness check decorative.
        """
        ahead = NOW + timedelta(seconds=FRESHNESS_SECONDS + 1)

        with pytest.raises(AuthError):
            verify(BODY, sign(BODY, SECRET), SECRET, signed_at=ahead, now=NOW)

    def test_the_window_is_short_enough_to_be_worth_having(self):
        assert 0 < FRESHNESS_SECONDS <= 900


class TestSecretFromEnvironment:
    def test_the_secret_is_read_from_the_environment(self):
        secret = secret_from_env({SECRET_ENV: "s3cret"})

        assert secret == b"s3cret"

    def test_a_missing_secret_is_a_refusal_not_an_empty_default(self):
        with pytest.raises(IngestNotConfigured) as caught:
            secret_from_env({})

        assert SECRET_ENV in str(caught.value)

    def test_a_blank_secret_is_a_refusal(self):
        """An exported-but-empty variable is the shape a broken deploy takes,
        and it must not read as "configured"."""
        for blank in ("", "   ", "\n"):
            with pytest.raises(IngestNotConfigured):
                secret_from_env({SECRET_ENV: blank})
