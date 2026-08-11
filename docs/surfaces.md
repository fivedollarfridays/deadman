# Real surfaces

`docs/ARCHITECTURE.md`'s "Surfaces (v1)" table describes the probes in the
abstract. This document is the concrete counterpart: which real path each
deployed surface watches, on which machine, how often, and what it means if
that surface goes dark. Every path below is collector configuration (see
`infra/collector/*.example.json`), never a literal compiled into this
package — nothing here describes Kevin's filesystem in source code.

## `cron:morning-brief`

- **Path:** `~/ops/data/brief-send-log.jsonl`, on the Mac only. The `ops`
  repo's own daily brief job appends one row to this log after a verified
  send.
- **Probe:** `deadman.probes.morning_brief.MorningBriefProbe`, reading the
  timestamp *inside* the newest row, never the file's mtime (a checkout or
  restore rewrites mtime without the brief having sent).
- **Cadence:** swept every 900s (15 min) by the `kevin-mac` collector. The
  probe's own tolerance is 30h (`DEFAULT_WINDOW_HOURS`) — a brief can run
  late without faulting, but a full missed day cannot.
- **What its blindness means:** this is the surface that justified the
  sprint. `tests/fixtures/real-morning-brief-fault.json` is this probe run
  for real against the actual log: no brief has sent since 2026-08-04,
  because `morning_brief_send.py` hangs and is killed by its own deadline
  guard, and nobody noticed for seven days because the brief is itself the
  alerting channel — a dead brief cannot report its own death. If this
  surface goes `UNOBSERVABLE` (the log or its directory disappears) rather
  than `FAULT`, that exact failure becomes invisible again.

## `host:mac/disk`

- **Path:** `/`, on the Mac.
- **Probe:** `deadman.probes.disk.DiskProbe`, configured with `host: "mac"`
  so its surface id cannot collide with the rig's.
- **Cadence:** swept every 900s by the `kevin-mac` collector, which also
  appends the trend sample the probe reasons over. A healthy *level* with a
  shrinking *rate* is a fault at 14 days of runway (`DEFAULT_RUNWAY_DAYS`),
  not when the volume actually fills.
- **What its blindness means:** the Mac runs the morning brief, the
  collector itself, and daily tooling. If disk pressure on the Mac goes
  unwatched, the failure mode is exactly the one this probe was built to
  stop repeating: a slow fill that never crosses a threshold check until it
  takes something down on a day that matters.

## `host:rig/disk`

- **Path:** `/`, on the rig — a second, physically separate machine, so a
  full Mac volume says nothing about it and vice versa.
- **Probe:** the same `DiskProbe` class as `host:mac/disk`, configured with
  `host: "rig"` instead. Adding this surface was a config file
  (`infra/collector/collector-rig.example.json`) plus an entry in
  `infra/collector/collectors.example.json` — no new probe code, which is
  the demonstration this task exists to make: a third machine, or a third
  volume on either machine, is the same shape again.
- **Cadence:** swept every 900s by its own `kevin-rig` collector — a second,
  independent process with its own liveness (see DM2.4), so one collector
  dying does not silence the other.
- **What its blindness means:** the rig holds the Vertex service-account
  credential this project's diagnosis layer depends on
  (`~/.deadman-creds/vertex-sa.json`, see `docs/HANDOFF.md`). Disk pressure
  there threatens that credential's storage and whatever else runs on the
  rig, invisibly, for exactly as long as nobody is watching the rig
  specifically rather than inferring its health from the Mac's.

## Collector liveness, one level up

Each surface above is only as trustworthy as the collector sweeping it. A
dead collector and a healthy estate produce the same empty inbox, so
`collector:kevin-mac` and `collector:kevin-rig` are themselves watched — see
DM2.4 and `docs/ARCHITECTURE.md`'s "The collector" section. A surface whose
newest evidence is older than its collector's declared cadence reads
`UNOBSERVABLE`, never `HEALTHY`: what was last heard is not news about now.

## Adding another surface

1. Point an existing probe at the new path in a collector's config file
   (`infra/collector/*.json`) — a new probe *type* is the only thing that
   requires new code, and none of the three surfaces above needed one.
2. Add the surface to that collector's entry in `collectors.example.json`
   (or the deployed `collectors.json`) so its liveness is declared, not
   inferred.
3. Document it here: path, cadence, and what its blindness would mean.
