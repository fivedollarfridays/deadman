# Captured real evidence

Unlike `tests/recorded/`, which replays authored-or-captured *model*
responses, this directory holds evidence a real probe produced against real
infrastructure. Nothing here is authored to look plausible.

`real-morning-brief-fault.json` is `MorningBriefProbe` run directly against
`~/ops/data/brief-send-log.jsonl` — the finding that justified this sprint
(see `docs/SPRINT-BRIEF-DM2.md`). It is not a fixture invented to exercise
the parser; it is what the probe actually said when pointed at the log this
session, still broken. `docs/surfaces.md` and DM2.9's case study read from
it rather than from memory.

Refresh it, if the underlying fault ever changes, with:

```bash
python3 -c "
from pathlib import Path
from deadman.probes.morning_brief import MorningBriefProbe
probe = MorningBriefProbe(log_path=Path.home() / 'ops' / 'data' / 'brief-send-log.jsonl')
print(probe.observe())
"
```

and update the committed JSON by hand — there is no capture script, on
purpose: this is a spot check of the real world at a moment in time, not
regenerated output a test can byte-compare against (see
`scripts/generate_samples.py` for that pattern, which applies to synthetic
demonstration data, not this).

`dm1-board-sample.json` is a different kind of frozen file: not a probe
capture but `sample-outputs/board.json` exactly as committed at the DM1
merge (`git show ef40500:sample-outputs/board.json`). It exists so
`tests/test_board_dm1_contract.py` can assert the deployed DM1 board's JSON
contract still holds — every key it promised is still present, additively —
without that check breaking every time the board legitimately grows a new
field. Never regenerate it; it is a record of what shipped, not of what the
code produces today.
