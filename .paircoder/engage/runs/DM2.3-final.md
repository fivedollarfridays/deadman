Everything is green: task marked \`done\`, all 4 gates clean, state.md updated. DM2.3 is complete.

## Summary

Built \`src/deadman/collector/\` — the process that sweeps configured probes on Kevin's machines and ships signed evidence to the DM2.2 ingest endpoint:

- **\`config.py\`** — probes and their arguments come from a JSON file (\`infra/collector/collector.example.json\`); a small \`PROBE_TYPES\` registry maps type names to real probe classes, with generic \`str→Path\` argument coercion read off each dataclass's own field annotations so a probe registered later needs no matching change here. Malformed config fails loudly, naming the offending key.
- **\`transport.py\`** — \`UrllibTransport\` (stdlib only) with a \`TransportError\` distinguishing "unreachable" from "answered but rejected."
- **\`spool.py\`** — store-and-forward with no in-process state: one file per undelivered batch, so a fresh \`Spool\`/\`Collector\` reconstructed over the same directory after a crash sees exactly what was left behind.
- **\`run.py\`** — orchestrates sweep → drain spool → deliver, reusing \`probes.base.sweep()\` for isolation. The key subtlety: every send (first attempt or Nth retry) is **freshly signed** at the current clock reading rather than replaying the original signature, since DM2.2's 5-minute freshness window would otherwise reject an honest retry after any real outage.
- **\`infra/launchd/com.deadman.collector.plist\`** + a documented install command in \`infra/README.md\`, with the shared secret sourced from an uncommitted \`~/.deadman/collector-env.sh\` file, matching DM2.2's existing "no secret committed" rule. Verified by hand (\`plutil -lint\`, live \`--dry-run\` run) but \`launchctl load\` itself was left for Kevin to run — not something to do unattended.

412/412 tests passing (up from 362), all four gates clean. \`state.md\` and the task file are updated; **DM2.4** (collector liveness) is next.