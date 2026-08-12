"""The DM1 board contract, still honored.

The JSON contract already has consumers deployed against DM1's shape.
``tests/test_sample_outputs.py`` pins the *current* generator output byte for
byte, which is the wrong tool for a compatibility question: it fails the
moment the board grows a field, which is exactly what this task does on
purpose. This asserts the narrower, permanent claim instead — every key DM1
ever promised is still there, additively, on a board built today.

``tests/fixtures/dm1-board-sample.json`` is ``sample-outputs/board.json`` as
committed at the DM1 merge (``git show ef40500:sample-outputs/board.json``),
frozen rather than regenerated: it is evidence of what DM1 shipped, not a
claim about what this code produces now.
"""

from __future__ import annotations

import json
from pathlib import Path

from deadman.probes.disk import DiskProbe
from deadman.probes.morning_brief import MorningBriefProbe
from deadman.service import build_board

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dm1-board-sample.json"
DM1_SAMPLE = json.loads(FIXTURE.read_text())


def _current_board(tmp_path: Path) -> dict:
    return build_board(
        [
            DiskProbe(history_path=tmp_path / "disk-history.jsonl"),
            MorningBriefProbe(log_path=tmp_path / "absent" / "morning-brief.jsonl"),
        ]
    )


def test_every_dm1_top_level_key_is_still_present(tmp_path: Path):
    board = _current_board(tmp_path)

    missing = set(DM1_SAMPLE) - set(board)

    assert not missing, f"DM1 board keys dropped: {missing}"


def test_every_dm1_surface_row_key_is_still_present(tmp_path: Path):
    board = _current_board(tmp_path)
    rows_by_surface = {row["surface"]: row for row in board["surfaces"]}

    for dm1_row in DM1_SAMPLE["surfaces"]:
        row = rows_by_surface[dm1_row["surface"]]
        missing = set(dm1_row) - set(row)
        assert not missing, f"{dm1_row['surface']}: DM1 row keys dropped: {missing}"


def test_every_dm1_surface_detail_key_is_still_present(tmp_path: Path):
    board = _current_board(tmp_path)
    rows_by_surface = {row["surface"]: row for row in board["surfaces"]}

    for dm1_row in DM1_SAMPLE["surfaces"]:
        row = rows_by_surface[dm1_row["surface"]]
        missing = set(dm1_row["detail"]) - set(row["detail"])
        assert not missing, f"{dm1_row['surface']}: DM1 detail keys dropped: {missing}"


def test_the_dm1_summary_counts_are_still_the_same_kind_of_number(tmp_path: Path):
    board = _current_board(tmp_path)

    for key in ("healthy_count", "fault_count", "blind_count"):
        assert isinstance(DM1_SAMPLE[key], int)
        assert isinstance(board[key], int)
