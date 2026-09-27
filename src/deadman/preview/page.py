"""The HTML preview page: Open Graph tags for unfurlers, the board for people.

Every string that came off the board is escaped. Board rows can originate in
ingested evidence, so a surface name or summary is untrusted text and must
never reach the page as markup.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from html import escape

from deadman.preview.card import CARD_HEIGHT, CARD_PATH, CARD_WIDTH

#: Overrides the request-derived base URL in ``og:url`` and ``og:image``.
PUBLIC_URL_ENV = "DEADMAN_PUBLIC_URL"

TITLE = "deadman"

#: The README's opening line, verbatim: the preview claims nothing the
#: project does not already say about itself.
DESCRIPTION = (
    "A monitor for the failures that do not page anyone: the ones where a "
    "system keeps reporting success and quietly stops doing its job."
)

_STYLE = (
    "body{background:#0f172a;color:#f1f5f9;font-family:system-ui,sans-serif;"
    "margin:2rem auto;max-width:60rem;padding:0 1rem}"
    "td,th{padding:.3rem .8rem;text-align:left;border-bottom:1px solid #475569}"
    "table{border-collapse:collapse}.fault{color:#fbbf24}a{color:#cbd5e1}"
)


def public_base_url(environ: dict) -> str:
    """Scheme and host the page's absolute URLs are built on, no trailing slash.

    ``DEADMAN_PUBLIC_URL`` wins when set. Otherwise the request says: Cloud
    Run terminates TLS in front of the container, so the scheme is read from
    ``X-Forwarded-Proto`` before the WSGI server's own (always ``http``).
    """
    configured = os.environ.get(PUBLIC_URL_ENV, "").strip()
    if configured:
        return configured.rstrip("/")
    forwarded = str(environ.get("HTTP_X_FORWARDED_PROTO", "")).split(",")[0].strip()
    scheme = forwarded or str(environ.get("wsgi.url_scheme", "http"))
    host = environ.get("HTTP_HOST") or (
        f"{environ.get('SERVER_NAME', 'localhost')}:{environ.get('SERVER_PORT', '80')}"
    )
    return f"{scheme}://{host}"


def render_page(board: dict[str, object], base_url: str) -> str:
    """The whole HTML document for one board."""
    meta = {
        "og:title": TITLE,
        "og:description": DESCRIPTION,
        "og:type": "website",
        "og:url": f"{base_url}/",
        "og:image": f"{base_url}{CARD_PATH}",
        "og:image:width": str(CARD_WIDTH),
        "og:image:height": str(CARD_HEIGHT),
        "og:image:alt": f"{TITLE}: a monitor for the failure that reports success",
        "twitter:card": "summary_large_image",
        "twitter:title": TITLE,
        "twitter:description": DESCRIPTION,
        "twitter:image": f"{base_url}{CARD_PATH}",
    }
    tags = "\n".join(_meta_tag(key, value) for key, value in meta.items())
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        f"<title>{escape(TITLE)}</title>\n"
        f'<meta name="description" content="{escape(DESCRIPTION)}">\n'
        f"{tags}\n<style>{_STYLE}</style></head>\n"
        f"<body><h1>{escape(TITLE)}</h1><p>{escape(DESCRIPTION)}</p>\n"
        f"{_summary(board)}\n{_rows(board)}\n"
        '<p><a href="/?format=json">This board as JSON</a></p>\n'
        "</body></html>\n"
    )


def respond_page(
    environ: dict, start_response: Callable, board: dict[str, object]
) -> Iterable[bytes]:
    """Serve :func:`render_page` for this request as ``text/html``."""
    body = render_page(board, public_base_url(environ)).encode("utf-8")
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Vary", "Accept, User-Agent"),
        ],
    )
    return [body]


def _meta_tag(key: str, value: str) -> str:
    attr = "name" if key.startswith("twitter:") else "property"
    return f'<meta {attr}="{escape(key)}" content="{escape(value)}">'


def _summary(board: dict[str, object]) -> str:
    counts = (
        f"{board.get('fault_count', 0)} fault, "
        f"{board.get('healthy_count', 0)} healthy, "
        f"{board.get('blind_count', 0)} blind"
    )
    return f"<p>{escape(counts)}</p>"


def _rows(board: dict[str, object]) -> str:
    surfaces = board.get("surfaces") or []
    cells = "".join(
        f'<tr class="{escape(str(row.get("observation", "")))}">'
        f"<td>{escape(str(row.get('surface', '')))}</td>"
        f"<td>{escape(str(row.get('observation', '')))}</td>"
        f"<td>{escape(str(row.get('summary', '')))}</td></tr>"
        for row in surfaces
        if isinstance(row, dict)
    )
    return (
        "<table><thead><tr><th>surface</th><th>observation</th><th>summary</th></tr>"
        f"</thead><tbody>{cells}</tbody></table>"
    )
