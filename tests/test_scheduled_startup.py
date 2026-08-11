"""Fail closed at startup when no scheduler secret is configured.

Mirrors ``tests/test_ingest_startup.py`` exactly, for the same reason: "the
service refuses to start" is a claim about a process, and a real subprocess
is what proves it rather than an in-process import that could be shadowed by
whatever the importer already had loaded.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from deadman.ingest.auth import SECRET_ENV as INGEST_SECRET_ENV
from deadman.scheduled.auth import SECRET_ENV

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(source: str, secret: str | None) -> subprocess.CompletedProcess[str]:
    environ = {k: v for k, v in os.environ.items() if k != SECRET_ENV}
    environ["PYTHONDONTWRITEBYTECODE"] = "1"
    # The ingest secret is a separate, already-mandatory prerequisite; keep it
    # supplied so this test isolates the scheduler secret's own refusal.
    environ.setdefault(INGEST_SECRET_ENV, "a-secret")
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
    def test_importing_the_service_without_a_scheduler_secret_fails(self):
        result = _run("import deadman.service", secret=None)

        assert result.returncode != 0
        assert "SchedulerNotConfigured" in result.stderr

    def test_the_refusal_names_the_variable_to_set(self):
        result = _run("import deadman.service", secret=None)

        assert SECRET_ENV in result.stderr

    def test_the_refusal_is_not_a_warning_that_leaves_an_app_serving(self):
        result = _run("import deadman.service as s; print('SERVING', s.app)", secret=None)

        assert "SERVING" not in result.stdout

    def test_the_service_starts_when_both_secrets_are_present(self):
        result = _run(
            "import deadman.service as s; print('OK', callable(s.app))", secret="a-secret"
        )

        assert result.returncode == 0, result.stderr
        assert "OK True" in result.stdout

    def test_a_blank_secret_is_not_a_configured_secret(self):
        result = _run("import deadman.service", secret="   ")

        assert result.returncode != 0
        assert "SchedulerNotConfigured" in result.stderr


class TestNothingSecretIsCommitted:
    """The scheduler secret's equivalent of the ingest scan.

    Ingest had this guard from DM2.2 and the scheduler secret shipped without
    one. It also needs a second pattern that ingest never did: this secret is
    documented as a Cloud Scheduler bearer, so it appears as
    ``Authorization=Bearer <value>`` as well as ``VAR=value``, and a scan
    written only for the latter would pass while a live token sat in the
    runbook.
    """

    #: Shapes that are not secrets. Short and enumerated on purpose: growing
    #: this list is the moment to ask whether a real value is being smuggled in.
    ALLOWED = ("$", "deadman-scheduler-secret:")

    def _matches(self, pattern: str, *paths: str) -> list[str]:
        found = subprocess.run(
            ["git", "grep", "-hI", "-o", "-E", pattern, "--", *(paths or (".",))],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return found.stdout.splitlines()

    def _assignments(self) -> list[str]:
        raw = self._matches(f"{SECRET_ENV}=[^\"'\x60 ]*")
        return [line.split("=", 1)[1] for line in raw]

    def _bearers(self) -> list[str]:
        # This file is excluded because it *contains* the bearer pattern as a
        # string literal, so the scan matches its own source and reports the
        # regex fragment as a committed token. The ingest scan avoids this by
        # delimiter choice; a bracketed character class cannot. The exclusion
        # is narrow and safe: ``_assignments`` above still scans this file for
        # the ``VAR=value`` shape, so a real secret pasted here is still caught.
        raw = self._matches(
            "Authorization=Bearer [^\"'\x60 ]*",
            ".",
            ":(exclude)tests/test_scheduled_startup.py",
        )
        return [line.split("Bearer ", 1)[1] for line in raw]

    def test_every_committed_assignment_resolves_rather_than_carrying_a_value(self):
        for value in self._assignments():
            if not value:
                continue
            assert value.startswith(self.ALLOWED), f"{SECRET_ENV} looks committed as {value!r}"

    #: ``$…`` resolves at run time; ``<…>`` is an angle-bracket placeholder in a
    #: runbook. Neither can be a live token, and a real one matches neither.
    ALLOWED_BEARERS = ("$", "<")

    def test_every_committed_bearer_resolves_rather_than_carrying_a_value(self):
        for value in self._bearers():
            if not value:
                continue
            assert value.startswith(self.ALLOWED_BEARERS), (
                f"a bearer token looks committed as {value!r}"
            )

    def test_the_scan_is_actually_finding_the_documented_assignments(self):
        """Guards the guard: a broken pattern would pass by finding nothing."""
        assert self._assignments(), "the secret scan matched nothing, so it proves nothing"
