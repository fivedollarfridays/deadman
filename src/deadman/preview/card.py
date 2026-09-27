"""The preview card image: a checked-in PNG, served as package data.

The image is rendered once by ``scripts/render_og_card.py`` and committed,
rather than drawn per request, because the package has zero runtime
dependencies and drawing text needs an imaging library. The service only
ever reads bytes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import cache
from importlib.resources import files

#: Where the card is served. Stable: a posted link's preview caches this URL.
CARD_PATH = "/og-card.png"

#: The card's pixel size, the Open Graph large-image ratio (1.91:1).
CARD_WIDTH = 1200
CARD_HEIGHT = 630

_CARD_RESOURCE = "og-card.png"


@cache
def card_bytes() -> bytes:
    """The card PNG, read from the installed package once per process."""
    return files("deadman.preview").joinpath(_CARD_RESOURCE).read_bytes()


def serve_card(environ: dict, start_response: Callable) -> Iterable[bytes]:
    """Answer ``GET`` or ``HEAD`` of :data:`CARD_PATH` with the card PNG.

    ``HEAD`` is answered because some unfurlers probe an image before
    fetching it; anything else is a 405, the same as the rest of the service.
    """
    method = environ.get("REQUEST_METHOD")
    if method not in ("GET", "HEAD"):
        body = b'{"error": "method not allowed"}'
        start_response(
            "405 Method Not Allowed",
            [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
        )
        return [body]
    data = card_bytes()
    start_response(
        "200 OK",
        [
            ("Content-Type", "image/png"),
            ("Content-Length", str(len(data))),
            ("Cache-Control", "public, max-age=86400"),
        ],
    )
    return [b""] if method == "HEAD" else [data]
