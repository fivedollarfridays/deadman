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
