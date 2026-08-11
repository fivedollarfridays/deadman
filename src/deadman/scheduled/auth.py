"""Who may trigger the scheduled self-check.

**A public endpoint that triggers work is a free denial-of-service.** ``GET /``
costs one sweep of the local probes and answers with what it already knows;
``POST /self-check`` costs the same sweep on demand, on every request, from
anyone who can reach the URL. Cloud Scheduler must be able to prove it is
Cloud Scheduler before this endpoint spends a single cycle.

There is no body to authenticate here — the trigger carries no payload, only
an instruction to run — so this is deliberately simpler than
:mod:`deadman.ingest.auth`'s HMAC-over-bytes scheme: a bearer token, compared
in constant time, is the whole check.

**A missing secret is a refusal, not a default.** Same rule as
:func:`deadman.ingest.auth.secret_from_env`, for the same reason: an
unconfigured deploy that started anyway would serve a trigger endpoint to
anyone who could reach it, and "self-check ran" would stop meaning anything.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Mapping

#: Environment variable holding the shared secret. The name is in the source;
#: the value never is.
SECRET_ENV = "DEADMAN_SCHEDULER_SECRET"

#: Header Cloud Scheduler is configured to send the shared secret in.
AUTHORIZATION_HEADER = "Authorization"

#: The WSGI spelling of :data:`AUTHORIZATION_HEADER`.
AUTHORIZATION_ENVIRON_KEY = "HTTP_AUTHORIZATION"

_SCHEME = "Bearer "


class SchedulerAuthError(Exception):
    """The request did not carry the shared secret this endpoint requires."""


class SchedulerNotConfigured(RuntimeError):
    """No shared secret is configured. Raised at startup, never at request time."""


_MISSING_SECRET = (
    f"{SECRET_ENV} is not set, so the scheduled self-check endpoint cannot tell "
    f"Cloud Scheduler from anyone else who can reach this URL. Refusing to start "
    f"rather than accepting unauthenticated triggers. Set {SECRET_ENV} to the "
    f"same value Cloud Scheduler's job sends as its bearer token."
)


def secret_from_env(environ: Mapping[str, str] | None = None) -> str:
    """The shared secret, or a refusal.

    Reads ``os.environ`` by default; the parameter exists so tests can pin the
    absent case without mutating global state, matching
    :func:`deadman.ingest.auth.secret_from_env`.
    """
    source = os.environ if environ is None else environ
    value = source.get(SECRET_ENV, "")
    if not value.strip():
        raise SchedulerNotConfigured(_MISSING_SECRET)
    return value


def check_secret(authorization: str | None, secret: str) -> None:
    """Raise :class:`SchedulerAuthError` unless ``authorization`` carries
    ``secret`` as a bearer token.

    Compared with :func:`hmac.compare_digest` rather than ``==`` so a wrong
    guess cannot be timed into a right one.
    """
    if authorization is None or not authorization.startswith(_SCHEME):
        raise SchedulerAuthError("missing or malformed Authorization header")
    provided = authorization[len(_SCHEME) :].strip()
    if not provided or not hmac.compare_digest(provided, secret):
        raise SchedulerAuthError("bearer token does not match")
