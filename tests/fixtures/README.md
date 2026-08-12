# Captured real evidence

Unlike `tests/recorded/`, which replays authored-or-captured *model*
responses, this directory holds evidence a real probe produced against real
infrastructure. Nothing here is authored to look plausible.

`real-morning-brief-fault.json` is `MorningBriefProbe` run directly against
`~/ops/data/brief-send-log.jsonl` — the finding that justified this sprint
(see `docs/SPRINT-BRIEF-DM2.md`). It is not a fixture invented to exercise
the parser; it is what the probe actually said when pointed at the log this
session, still broken. `docs/surfaces.md` and the case study in
`docs/PROOF.md` read from it rather than from memory — `tests/test_proof_doc.py`
enforces that every number in the case study is findable here.

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

`real-board-capture.json` is the same kind of capture one level up: `GET /`
against the deployed Cloud Run service, unedited, with the response's own
status and time recorded beside it. It exists because `docs/PROOF.md` claims
the outage above reached a public board through a real collector, and a board
generated locally would prove the code works while proving nothing about
whether the estate is watched. Refresh it, if it is ever worth refreshing,
with:

```bash
curl -sS https://deadman-mrapac5nda-uc.a.run.app/ | python3 -m json.tool
```

and update the `board` key by hand, along with `captured_at`, `http_status`
and the served image tag (`gcloud run services describe deadman
--region=us-central1 --format='value(spec.template.spec.containers[0].image)'`).
`tests/test_proof_doc.py` will fail if `docs/PROOF.md` still quotes numbers the
new capture does not contain, which is the intended way to find out.

`dm1-board-sample.json` is a different kind of frozen file: not a probe
capture but `sample-outputs/board.json` exactly as committed at the DM1
merge (`git show ef40500:sample-outputs/board.json`). It exists so
`tests/test_board_dm1_contract.py` can assert the deployed DM1 board's JSON
contract still holds — every key it promised is still present, additively —
without that check breaking every time the board legitimately grows a new
field. Never regenerate it; it is a record of what shipped, not of what the
code produces today.
