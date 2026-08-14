"""Locks the Baserow backup probe's distinguishing behavior.

The artifact is the evidence: the probe lists the backup volume inside the
container and rules on the timestamp *encoded in the newest filename*
(``baserow_backup_YYYYMMDD_HHMMSS.tar.gz``, stamped by the backup script in
the machine's local time). A green cron log proves the scheduler said
"complete"; only the artifact proves a backup exists. This probe was written
the same day a repointed worktree path had the backup cron silently failing
for two days behind an installed crontab line.

Docker being unreachable, the container being down, or a listing that cannot
be parsed are all UNOBSERVABLE — the instrument is blind, the backups are not
known-broken. An empty volume or a stale newest artifact is a FAULT.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from deadman.evidence.model import Observation
from deadman.probes.baserow_backup import _LOCAL_TZ, BaserowBackupProbe


def _stamp(dt: datetime) -> str:
    return f"baserow_backup_{dt.strftime('%Y%m%d_%H%M%S')}.tar.gz"


def _probe(listing=None, returncode=0, error=None, **kw):
    def fake_run(argv):
        if error is not None:
            raise error
        return returncode, listing or ""

    return BaserowBackupProbe(run_cmd=fake_run, **kw)


def _now_local() -> datetime:
    return datetime.now(_LOCAL_TZ)


def test_fresh_backup_is_healthy_and_names_the_artifact() -> None:
    newest = _now_local() - timedelta(hours=2)
    listing = "\n".join([_stamp(newest - timedelta(days=1)), _stamp(newest)])

    evidence = _probe(listing=listing).observe()

    assert evidence.observation is Observation.HEALTHY
    assert evidence.detail["newest"] == _stamp(newest)
    assert evidence.detail["backup_count"] == 2


def test_stale_newest_backup_is_fault_even_with_many_old_backups() -> None:
    stale = _now_local() - timedelta(days=3)
    listing = "\n".join(_stamp(stale - timedelta(days=n)) for n in range(5))

    evidence = _probe(listing=listing).observe()

    assert evidence.observation is Observation.FAULT
    assert "72" in evidence.summary  # names the age in hours


def test_empty_volume_is_fault_no_backup_has_ever_existed() -> None:
    evidence = _probe(listing="").observe()
    assert evidence.observation is Observation.FAULT


def test_unparseable_names_only_is_unobservable_not_fault() -> None:
    evidence = _probe(listing="lost+found\nreadme.txt").observe()
    assert evidence.observation is Observation.UNOBSERVABLE


def test_docker_error_is_unobservable_with_stderr_context() -> None:
    evidence = _probe(returncode=1, listing="Error: no such container").observe()
    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.FAULT


def test_docker_binary_missing_is_unobservable() -> None:
    evidence = _probe(error=FileNotFoundError("docker")).observe()
    assert evidence.observation is Observation.UNOBSERVABLE


def test_default_runner_is_real_subprocess() -> None:
    # The injectable runner exists for tests; the default must actually run
    # a command and hand back (returncode, output).
    probe = BaserowBackupProbe()
    code, out = probe.run_cmd(["sh", "-c", "echo listing"])
    assert code == 0
    assert out.strip() == "listing"


def test_listing_command_is_direct_argv_with_no_shell() -> None:
    """The backups_dir is config-controlled; it must reach `ls` as a plain
    argument, never interpolated into a shell string."""
    seen = []

    def spy_run(argv):
        seen.append(argv)
        return 0, _stamp(_now_local())

    BaserowBackupProbe(run_cmd=spy_run, backups_dir="/b; rm -rf /").observe()

    (argv,) = seen
    assert "sh" not in argv
    assert "-c" not in argv
    assert argv[-1] == "/b; rm -rf /"  # one argument, verbatim, not a script
