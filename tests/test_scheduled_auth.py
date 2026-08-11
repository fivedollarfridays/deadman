"""Scheduled-endpoint authentication: a bearer token, and a secret that must
exist before the service will start.

Simpler than :mod:`deadman.ingest.auth` on purpose — there is no body to
authenticate, only an instruction to run — but the same two properties are
being pinned: the secret comes from the environment and its absence is a
refusal, not a default, and a wrong or missing token is rejected.
"""

from __future__ import annotations

import pytest

from deadman.scheduled.auth import (
    SECRET_ENV,
    SchedulerAuthError,
    SchedulerNotConfigured,
    check_secret,
    secret_from_env,
)

SECRET = "correct-horse-battery-staple"


class TestCheckSecret:
    def test_a_matching_bearer_token_is_accepted(self):
        check_secret(f"Bearer {SECRET}", SECRET)

    def test_a_wrong_token_is_refused(self):
        with pytest.raises(SchedulerAuthError):
            check_secret("Bearer wrong-token", SECRET)

    def test_a_missing_header_is_refused(self):
        with pytest.raises(SchedulerAuthError):
            check_secret(None, SECRET)

    def test_a_header_without_the_bearer_scheme_is_refused(self):
        with pytest.raises(SchedulerAuthError):
            check_secret(SECRET, SECRET)

    def test_an_empty_bearer_token_is_refused(self):
        with pytest.raises(SchedulerAuthError):
            check_secret("Bearer ", SECRET)

    def test_a_bearer_token_that_is_a_prefix_of_the_secret_is_refused(self):
        with pytest.raises(SchedulerAuthError):
            check_secret(f"Bearer {SECRET[:-1]}", SECRET)


class TestSecretFromEnvironment:
    def test_the_secret_is_read_from_the_environment(self):
        secret = secret_from_env({SECRET_ENV: "s3cret"})

        assert secret == "s3cret"

    def test_a_missing_secret_is_a_refusal_not_an_empty_default(self):
        with pytest.raises(SchedulerNotConfigured) as caught:
            secret_from_env({})

        assert SECRET_ENV in str(caught.value)

    def test_a_blank_secret_is_a_refusal(self):
        for blank in ("", "   ", "\n"):
            with pytest.raises(SchedulerNotConfigured):
                secret_from_env({SECRET_ENV: blank})
