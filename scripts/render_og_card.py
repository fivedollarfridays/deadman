"""Render the board's link-preview card: ``src/deadman/preview/og-card.png``.

Run this when the card's wording or colours change, then commit the PNG:

    pip install -e '.[card]'
    python scripts/render_og_card.py

The service never runs this. It serves the committed bytes (see
``deadman.preview.card``), which keeps Pillow out of the runtime and out of
the test run; the package still declares zero runtime dependencies.

Colours are the slate and amber of ``docs/architecture.svg``. The font is
Pillow's bundled default, so the output does not depend on which fonts the
machine rendering it happens to have.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
BACKGROUND = "#0f172a"
TITLE_COLOUR = "#f1f5f9"
LINE_COLOUR = "#cbd5e1"
ACCENT = "#b45309"

TITLE = "deadman"
LINE = "a monitor for the failure that reports success"

OUT = Path(__file__).resolve().parent.parent / "src" / "deadman" / "preview" / "og-card.png"


def render(out: Path = OUT) -> Path:
    """Draw the card and write it to ``out``."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    margin = 96
    draw.rectangle((0, 0, 24, HEIGHT), fill=ACCENT)
    draw.text((margin, 190), TITLE, font=ImageFont.load_default(size=150), fill=TITLE_COLOUR)
    draw.text((margin, 390), LINE, font=ImageFont.load_default(size=46), fill=LINE_COLOUR)
    draw.rectangle((margin, 470, margin + 160, 478), fill=ACCENT)
    image.save(out, format="PNG", optimize=True)
    return out


if __name__ == "__main__":
    print(render(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT))
