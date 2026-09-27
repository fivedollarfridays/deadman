"""The board as a link preview: HTML with Open Graph tags, and its card image.

``GET /`` answers JSON to every existing client. This package decides when it
should answer HTML instead (:mod:`.negotiate`), renders that page
(:mod:`.page`), and serves the preview card image (:mod:`.card`).
"""

from deadman.preview.card import CARD_HEIGHT, CARD_PATH, CARD_WIDTH, card_bytes, serve_card
from deadman.preview.negotiate import UNFURLER_AGENTS, wants_html
from deadman.preview.page import (
    DESCRIPTION,
    PUBLIC_URL_ENV,
    TITLE,
    public_base_url,
    render_page,
    respond_page,
)

__all__ = [
    "CARD_HEIGHT",
    "CARD_PATH",
    "CARD_WIDTH",
    "DESCRIPTION",
    "PUBLIC_URL_ENV",
    "TITLE",
    "UNFURLER_AGENTS",
    "card_bytes",
    "public_base_url",
    "render_page",
    "respond_page",
    "serve_card",
    "wants_html",
]
