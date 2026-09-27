"""The preview card: a 1200x630 PNG the installed package carries and serves.

Dimensions are read from the PNG header with the stdlib, so the suite needs
no imaging library. The one test that re-renders the card through
``scripts/render_og_card.py`` skips when Pillow is absent, as it is in CI.
"""

from __future__ import annotations

import importlib.util
import struct
import tomllib
from pathlib import Path

import pytest

from deadman.preview import CARD_HEIGHT, CARD_WIDTH, card_bytes

_ROOT = Path(__file__).resolve().parent.parent
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == _PNG_SIGNATURE
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_the_card_is_a_1200_by_630_png() -> None:
    assert (CARD_WIDTH, CARD_HEIGHT) == (1200, 630)
    assert _png_size(card_bytes()) == (1200, 630)


def test_the_card_stays_small_enough_for_every_unfurler() -> None:
    """LinkedIn and X both refuse preview images over 5 MB."""
    assert len(card_bytes()) < 1_000_000


def test_the_card_ships_in_the_installed_package() -> None:
    """The Dockerfile installs the package non-editable, so an undeclared
    data file would be missing from the image while every test still passed
    against the source tree."""
    config = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    package_data = config["tool"]["setuptools"]["package-data"]
    assert "og-card.png" in package_data["deadman.preview"]


def test_the_render_script_draws_a_card_of_the_right_size(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    spec = importlib.util.spec_from_file_location(
        "render_og_card", _ROOT / "scripts" / "render_og_card.py"
    )
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    out = tmp_path / "card.png"
    script.render(out)

    assert _png_size(out.read_bytes()) == (1200, 630)
