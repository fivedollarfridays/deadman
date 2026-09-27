"""Who gets the HTML preview page and who keeps getting the JSON board.

The JSON board is a contract: the ops board watcher and every script that
reads ``GET /`` send no ``Accept`` header at all, or ``*/*``. HTML goes only
to a caller that asked for it by name, or to a link unfurler, which never
sends an Accept header worth trusting but always names itself.
"""

from __future__ import annotations

import pytest

from deadman.preview import wants_html

_CHROME_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
)


def _env(accept: str | None = None, agent: str | None = None) -> dict[str, str]:
    environ: dict[str, str] = {}
    if accept is not None:
        environ["HTTP_ACCEPT"] = accept
    if agent is not None:
        environ["HTTP_USER_AGENT"] = agent
    return environ


@pytest.mark.parametrize(
    "accept, agent",
    [
        (None, None),
        (None, "curl/8.7.1"),
        ("*/*", "curl/8.7.1"),
        (None, "Python-urllib/3.11"),
        ("application/json", None),
        ("application/json, text/html", None),
        ("text/html;q=0.5, application/json", None),
        ("text/html;q=0", None),
        ("", None),
    ],
)
def test_machine_callers_keep_the_json_board(accept: str | None, agent: str | None) -> None:
    assert wants_html(_env(accept, agent)) is False


@pytest.mark.parametrize(
    "accept",
    [
        "text/html",
        _CHROME_ACCEPT,
        "application/json;q=0.5, text/html",
        "TEXT/HTML",
    ],
)
def test_a_caller_that_prefers_html_gets_html(accept: str) -> None:
    assert wants_html(_env(accept)) is True


@pytest.mark.parametrize(
    "agent",
    [
        "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)",
        "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
        "Twitterbot/1.0",
    ],
)
def test_link_unfurlers_get_html_whatever_they_accept(agent: str) -> None:
    assert wants_html(_env("*/*", agent)) is True
    assert wants_html(_env(None, agent)) is True


@pytest.mark.parametrize("query", ["format=json", "a=1&format=json", "format=JSON"])
def test_format_json_in_the_query_always_gets_json(query: str) -> None:
    """The page links here, so a browser reader can still see the raw board."""
    environ = _env(_CHROME_ACCEPT, "LinkedInBot/1.0")
    environ["QUERY_STRING"] = query
    assert wants_html(environ) is False
