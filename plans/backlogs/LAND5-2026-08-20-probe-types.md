# LAND5 — Two probe types the estate proved it needs (2026-08-20)

**Base:** main

From the Cerberry pipeline week (ops canon:
`~/ops/docs/social-pipeline/GUIDE.md` §8b incident-to-invariant). Two
failure classes were caught this week that deadman COULD NOT HAVE
EXPRESSED as surfaces — each was worked around with hand-rolled ops-side
code. A workaround in the wrong repo is the signal that a probe type is
missing.

Doctrine held throughout: probes never raise; UNOBSERVABLE (our
instrument is blind) is never FAULT (the surface is broken); evidence
comes from inside the artifact, never from mtime.

---

### LAND5.1 — `public_path` probe: liveness of the PATH, not the process | Cx: 2 | P1

**Description:** The estate has repeatedly failed with a healthy process
behind a dead path: the arena served public 502s under a KeepAlive'd
tunnel (8/11); toombos had the same topology; and Kevin never once saw
the staging queue because every link he was sent pointed at `:8899`
while the server sat healthy on `:8907` (found 8/19). ops hand-rolled
`bin/staging-watchdog.sh` to probe the full Tailscale Serve path because
no deadman probe could ask "does the address a human is given actually
answer?"

This probe fetches a URL through its real front door and rules on the
response. `Method.DESTINATION_PUBLIC` already describes exactly this
trust level ("a 200 on a permalink is real evidence from the
destination"). Not a heartbeat reader: the artifact IS the response.

**AC:**
- [ ] `src/deadman/probes/public_path.py`, frozen dataclass, Probe protocol
- [ ] 2xx (configurable expected status) → HEALTHY naming status + latency
- [ ] Non-2xx → FAULT naming the status (a 502 is evidence, not blindness)
- [ ] Timeout / DNS / connection refused → UNOBSERVABLE (we learned about
      our own reachability, not the surface) — this distinction is the
      whole point and must be tested both ways
- [ ] Optional `expect_substring`: a 200 serving the wrong body is a FAULT
      (a parked page answers 200)
- [ ] Registered in `PROBE_TYPES` as `public_path`
- [ ] Tests cover: 200 healthy, 502 fault, timeout unobservable, wrong-body
      fault, never-raises under a hostile transport

### LAND5.2 — `series_row` probe: today's row exists in a series artifact | Cx: 2 | P1

**Description:** kai-studio's devpost tracker (the fwdao contract's #1
metric) writes a SERIES — `[{"date": ..., "count": ...}]` — whose failure
mode is writing NO row (unknown-never-zero, correctly). It is not a
heartbeat, so `json_heartbeat` cannot read it, and ops had to write
`bin/devpost-rail-adapter.py` purely to translate "today's row exists"
into a heartbeat file deadman could see. That adapter is a workaround;
this probe is the durable home, and the adapter retires when it lands.

**AC:**
- [ ] `src/deadman/probes/series_row.py`, config args: path, surface_id,
      `date_key`, `timezone` (rows are stamped in local calendar days —
      America/Chicago here — and a UTC read would false-alarm every evening)
- [ ] Row for the expected date present → HEALTHY, row payload in bounded detail
- [ ] Absent inside an existing directory → FAULT ("the tracker did not run")
- [ ] Missing dir / unreadable / not-a-list / unparseable → UNOBSERVABLE
- [ ] Bounded extras, same caps as json_heartbeat (an artifact written by a
      process we do not control must never ride verbatim into the batch)
- [ ] Registered in `PROBE_TYPES` as `series_row`
- [ ] Tests cover each verdict + the timezone boundary case

### LAND5.3 — Retire the ops-side adapter + declare both surfaces | Cx: 1 | P2

**Description:** Once LAND5.2 ships: point kevin-mac's collector at the
prod series file directly via `series_row`, and retire
`~/ops/bin/devpost-rail-adapter.py` + `com.bpsai.devpost-rail` (ops-side
work, coordinated). Also fold the staging-queue surface onto `public_path`
so the probe reads the same path a phone takes. NOTE: ops keeps its own
freshness rails either way — the two watchers are deliberately redundant.

**AC:**
- [ ] Collector config uses the new probe types
- [ ] ops adapter + plist retired in the same change window (ops closes its
      ledger rows with evidence)
