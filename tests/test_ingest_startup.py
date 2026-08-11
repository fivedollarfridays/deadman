"""Fail closed at startup when no shared secret is configured.

These run the real thing as a real process, for the same reason DM1.11's
``deadman-self-check`` tests do: "refuses to start" is a claim about a
process, and asserting it against an in-process import would prove something
weaker than what a deploy actually does.

The failure being designed against is quiet. An unconfigured deploy that
started anyway would serve an ingest endpoint accepting anything, and the
board would then show a monitored estate that was in fact whatever the last
caller said it was. A service that will not boot is loud, and loud is
recoverable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from deadman.ingest.auth import SECRET_ENV

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(source: str, secret: str | None) -> subprocess.CompletedProcess[str]:
    environ = {k: v for k, v in os.environ.items() if k != SECRET_ENV}
    environ["PYTHONDONTWRITEBYTECODE"] = "1"
    if secret is not None:
        environ[SECRET_ENV] = secret
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPO_ROOT,
        env=environ,
        capture_output=True,
        text=True,
        check=False,
    )


class TestStartupRefusal:
    def test_importing_the_service_without_a_secret_fails(self):
        result = _run("import deadman.service", secret=None)

        assert result.returncode != 0
        assert "IngestNotConfigured" in result.stderr

    def test_the_refusal_names_the_variable_to_set(self):
        result = _run("import deadman.service", secret=None)

        assert SECRET_ENV in result.stderr

    def test_the_refusal_is_not_a_warning_that_leaves_an_app_serving(self):
        """The specific bad outcome: importing succeeds and ``app`` exists."""
        result = _run("import deadman.service as s; print('SERVING', s.app)", secret=None)

        assert "SERVING" not in result.stdout

    def test_the_service_starts_when_the_secret_is_present(self):
        result = _run(
            "import deadman.service as s; print('OK', callable(s.app))", secret="a-secret"
        )

        assert result.returncode == 0, result.stderr
        assert "OK True" in result.stdout

    def test_a_blank_secret_is_not_a_configured_secret(self):
        result = _run("import deadman.service", secret="   ")

        assert result.returncode != 0
        assert "IngestNotConfigured" in result.stderr


class TestNothingSecretIsCommitted:
    """The variable may be named anywhere; a value may never be committed.

    A bare ``git grep`` for the variable name cannot work here, because a
    runbook that tells an operator how to set it necessarily contains
    ``DEADMAN_INGEST_SECRET=`` — and a test that fails on its own
    documentation gets deleted rather than fixed. So the rule is about the
    *value*: every committed assignment must resolve at run time, from a shell
    variable or a Secret Manager reference. A pasted token matches none of
    those and fails.
    """

    #: Shapes that are not secrets. Short and enumerated on purpose: growing
    #: this list is the moment to ask whether a real value is being smuggled in.
    ALLOWED = ("$", "deadman-ingest-secret:")

    def _assignments(self) -> list[str]:
        found = subprocess.run(
            ["git", "grep", "-hI", "-o", "-E", f"{SECRET_ENV}=[^\"' ]*", "--", "."],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return [line.split("=", 1)[1] for line in found.stdout.splitlines()]

    def test_every_committed_assignment_resolves_rather_than_carrying_a_value(self):
        for value in self._assignments():
            assert value.startswith(self.ALLOWED), f"{SECRET_ENV} looks committed as {value!r}"

    def test_the_scan_is_actually_finding_the_documented_assignments(self):
        """Guards the guard: a broken pattern would pass by finding nothing."""
        assert self._assignments(), "the secret scan matched nothing, so it proves nothing"
