"""Deciding whether a ``GET`` of the board is answered with HTML or JSON.

The JSON board is the product's contract with its readers — the ops board
watcher, scripts, the tests — and none of them ask for anything in
particular: they send no ``Accept`` header, or ``*/*``. So JSON stays the
answer to every request that does not name HTML, and to every request that
names both at equal weight. A tie keeps today's behaviour, because changing
what an existing client receives is the one outcome this module must not
produce.

HTML goes to two kinds of caller. A browser, which lists ``text/html``
explicitly and above ``application/json``. And a link unfurler, which is
matched by its user agent instead, because unfurlers are inconsistent about
``Accept`` and entirely consistent about naming themselves: without the page
they read Open Graph tags from, a posted link renders as a bare URL.
"""

from __future__ import annotations

from urllib.parse import parse_qs

#: Lowercased user-agent fragments of the link unfurlers that read Open Graph
#: tags. Matching is a substring test, so version suffixes do not matter.
UNFURLER_AGENTS: tuple[str, ...] = (
    "linkedinbot",
    "facebookexternalhit",
    "slackbot",
    "twitterbot",
)


def wants_html(environ: dict) -> bool:
    """True when this request should get the HTML preview page, not JSON.

    ``?format=json`` always gets JSON, whoever asks: the page links there so
    a person in a browser can still read the raw board.
    """
    formats = parse_qs(str(environ.get("QUERY_STRING", ""))).get("format", [])
    if any(value.lower() == "json" for value in formats):
        return False
    agent = str(environ.get("HTTP_USER_AGENT", "")).lower()
    if any(fragment in agent for fragment in UNFURLER_AGENTS):
        return True
    weights = _accept_weights(str(environ.get("HTTP_ACCEPT", "")))
    html = weights.get("text/html", 0.0)
    return html > 0.0 and html > weights.get("application/json", 0.0)


def _accept_weights(header: str) -> dict[str, float]:
    """Media type -> quality, from an ``Accept`` header.

    Only exact types are recorded. Wildcards are deliberately ignored: ``*/*``
    says the caller will take anything, which is not a preference for HTML,
    and treating it as one would hand curl a web page.
    """
    weights: dict[str, float] = {}
    for item in header.split(","):
        media, _, params = item.strip().partition(";")
        media = media.strip().lower()
        if media and "*" not in media:
            weights[media] = _quality(params)
    return weights


def _quality(params: str) -> float:
    for param in params.split(";"):
        key, _, value = param.strip().partition("=")
        if key.strip().lower() == "q":
            try:
                return float(value)
            except ValueError:
                return 0.0
    return 1.0
