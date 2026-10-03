# DISK1 — the rig's disk surface watches the volume that actually filled (2026-10-03)

**Base:** disk1-base
**Type:** bugfix

## Why — two overnight losses deadman declared itself able to see

On 2026-10-02 03:39 and 2026-10-03 09:26 CT the rig's Windows `C:` volume reached zero free. The WSL disk
(`ext4.vhdx`, a file on `C:`) could not grow and every WSL process died at once with SIGBUS. Two overnight runs
were lost and nothing paged.

`host:rig/disk` exists for exactly this, and it would have read HEALTHY through both: it watches `/` — the ext4
filesystem INSIDE the vhdx, 27% used — while the volume that filled is the one the vhdx file sits on, visible from
the rig as `/mnt/c`. A second finding sits under it: no `kevin-rig` collector is installed on the rig at all (no
cron line, no unit), so the surface has been UNOBSERVABLE the whole time, and both `spool_dir` and
`history_path` in the rig example point under `/tmp`, which WSL empties on every restart — the trend this probe
exists to read would have been thrown away at each of the crashes it should have predicted.

Doctrine held: probes never raise; UNOBSERVABLE is never FAULT; no new probe type — `DiskProbe` already derives
`host:rig/disk/mnt/c` from `host` + `volume`.

## Decisions (coordinator)

1. **Two more disk probes in `infra/collector/collector-rig.example.json`**: `volume: /mnt/c` and `volume: /mnt/e`
   (`host: rig`), beside the existing `/`. Surface ids are whatever `DiskProbe.surface` derives
   (`host:rig/disk/mnt/c`, `host:rig/disk/mnt/e`) — read them from the probe, do not hand-type them.
2. **Each probe has its own `history_path`, and none of the rig's state lives under `/tmp`.** `spool_dir` and
   the three history files move to `~/.local/state/deadman/` (expanded by the config loader if it already
   expands `~`; if it does not, that is the one code change this lane makes, tested). Sharing one history file
   between volumes would mix three series into one slope.
3. **`infra/collector/collectors.example.json` declares all three surfaces for `kevin-rig`**, so liveness is
   declared, not inferred. The deployed `collectors.json` is changed in the same commit if it is tracked.
4. **`docs/surfaces.md` says what was blind and why**: a section per new surface (path, cadence, what its
   blindness means — "the WSL disk cannot grow; everything on the rig dies at once"), and one paragraph under
   `host:rig/disk` stating that `/` alone read HEALTHY through both losses.
5. **The install is written down as a runnable block and is the owner's step** (it needs the ingest secret):
   `infra/README.md` "Installing on a second machine (the rig)" gains the exact cron line / unit, the env file
   the secret is read from, and the one command that proves the first sweep landed. The completion entry lists
   "collector installed on the rig; first sweep read off the board" as OWED to the owner.

## Rules

TDD; run tests in the FOREGROUND and wait — never background a test, never end a turn "waiting". Follow this
repo's `CLAUDE.md` and `AGENTS.md`. No real network and no real `/mnt/c` in tests (the example config is LOADED
and its probes BUILT, as `tests/test_collector_example_config.py` already does — not observed). Never
`git add -A`/`git stash`; stage explicit paths. Lint/format/arch gates as this repo's CI runs them, clean on every
touched file. No secrets, home paths or personal addresses in any committed file (see the redaction pass, #30).
Complete with `bpsai-pair task update DISK1.1 --status done --conflicts-encountered <none | one flag per tension>`.

### DISK1.1 — `/mnt/c` and `/mnt/e` on the rig collector; state out of `/tmp`; the install written down | Cx: 2 | P0
**Model:** claude-sonnet-5
**Depends on:** none

**Description:** Decisions 1–5. Failing tests first: (a) the rig example config loads and builds THREE
`DiskProbe`s whose surfaces are `host:rig/disk`, `host:rig/disk/mnt/c`, `host:rig/disk/mnt/e`; (b) the three
`history_path`s are pairwise distinct and none of them, nor `spool_dir`, is under `/tmp`; (c)
`collectors.example.json`'s `kevin-rig` entry lists exactly the surfaces the built probes report (compared
against the probes, so the two files cannot drift); (d) if `~` expansion was added to the loader, a config with
`~/x` resolves under the home directory and one without is unchanged; (e) `docs/surfaces.md` names all three rig
surfaces (a doc test in the style the repo already uses, if one exists — otherwise assert the ids appear).
**AC:**
- [ ] (a)–(e) red-then-green; full suite green; lint/format clean
- [ ] `infra/README.md` carries the install block and the proof command; the owner step is listed as OWED in the completion entry

| Task | Cx | Pri | Model | Depends | Notes |
|---|---|---|---|---|---|
| DISK1.1 | 2 | P0 | sonnet | — | `/mnt/c` + `/mnt/e` disk probes on the rig; state out of `/tmp`; install block |
