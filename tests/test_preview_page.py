"""The HTML preview page: the tags an unfurler reads, and the board a human reads.

Parsed with the stdlib HTML parser rather than substring-matched, so a tag
that is present but malformed, or present only inside escaped text, fails.
"""

from __future__ import annotations

from html.parser import HTMLParser

import pytest

from deadman.preview import CARD_PATH, DESCRIPTION, TITLE, public_base_url, render_page

_BASE = "https://board.example.test"


def _board(**overrides: object) -> dict[str, object]:
    board: dict[str, object] = {
        "surfaces": [
            {
                "surface": "cron:morning-brief",
                "observation": "fault",
                "summary": "no brief sent since 2026-08-04",
                "held_seconds": 90.0,
            },
            {
                "surface": "host:disk",
                "observation": "healthy",
                "summary": "82% free",
                "held_seconds": 0.0,
            },
        ],
        "blind_spots": [],
        "healthy_count": 1,
        "fault_count": 1,
        "blind_count": 0,
    }
    board.update(overrides)
    return board


class _Meta(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, str] = {}
        self.text: list[str] = []
        self.elements: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append(tag)
        if tag == "meta":
            found = dict(attrs)
            key = found.get("property") or found.get("name")
            if key:
                self.tags[key] = found.get("content") or ""

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def _parse(html: str) -> _Meta:
    parser = _Meta()
    parser.feed(html)
    return parser


def test_the_page_carries_every_tag_an_unfurler_reads() -> None:
    tags = _parse(render_page(_board(), _BASE)).tags

    assert tags["og:title"] == TITLE
    assert tags["og:description"] == DESCRIPTION
    assert tags["og:url"] == f"{_BASE}/"
    assert tags["og:image"] == f"{_BASE}{CARD_PATH}"
    assert tags["og:image:width"] == "1200"
    assert tags["og:image:height"] == "630"
    assert tags["og:type"] == "website"
    assert tags["twitter:card"] == "summary_large_image"


def test_the_preview_text_is_the_readme_wording() -> None:
    assert TITLE == "deadman"
    assert DESCRIPTION == (
        "A monitor for the failures that do not page anyone: the ones where a "
        "system keeps reporting success and quietly stops doing its job."
    )


def test_the_page_shows_the_board_it_describes() -> None:
    text = " ".join(_parse(render_page(_board(), _BASE)).text)

    assert "cron:morning-brief" in text
    assert "no brief sent since 2026-08-04" in text
    assert "1 fault" in text and "1 healthy" in text and "0 blind" in text


def test_board_strings_are_escaped_never_rendered_as_markup() -> None:
    hostile = "<script>alert(1)</script>"
    board = _board(
        surfaces=[{"surface": hostile, "observation": "fault", "summary": f'"{hostile}'}]
    )

    parsed = _parse(render_page(board, _BASE))

    assert "script" not in parsed.elements
    assert hostile in " ".join(parsed.text)


@pytest.mark.parametrize(
    "environ, expected",
    [
        ({"wsgi.url_scheme": "http", "HTTP_HOST": "localhost:8080"}, "http://localhost:8080"),
        (
            {
                "wsgi.url_scheme": "http",
                "HTTP_HOST": "board.example.test",
                "HTTP_X_FORWARDED_PROTO": "https",
            },
            "https://board.example.test",
        ),
        (
            {"wsgi.url_scheme": "http", "SERVER_NAME": "board.example.test", "SERVER_PORT": "80"},
            "http://board.example.test:80",
        ),
    ],
)
def test_the_base_url_comes_from_the_request_when_not_configured(
    environ: dict[str, str], expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEADMAN_PUBLIC_URL", raising=False)
    assert public_base_url(environ) == expected


def test_a_configured_public_url_wins_over_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEADMAN_PUBLIC_URL", "https://deadman.example.test/")
    environ = {"wsgi.url_scheme": "http", "HTTP_HOST": "attacker.example.test"}

    assert public_base_url(environ) == "https://deadman.example.test"


@pytest.mark.parametrize(
    "environ",
    [
        {"HTTP_HOST": "evil.example.test/<x>", "HTTP_X_FORWARDED_PROTO": "https"},
        {"HTTP_HOST": "evil example", "HTTP_X_FORWARDED_PROTO": "https"},
        {"HTTP_HOST": "", "HTTP_X_FORWARDED_PROTO": "https"},
    ],
)
def test_a_malformed_host_header_is_not_echoed(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEADMAN_PUBLIC_URL", raising=False)
    environ = {"wsgi.url_scheme": "http", "SERVER_NAME": "board.internal", **environ}
    environ["SERVER_PORT"] = "8080"

    assert public_base_url(environ) == "https://board.internal:8080"


def test_a_forwarded_proto_that_is_not_http_or_https_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEADMAN_PUBLIC_URL", raising=False)
    environ = {
        "wsgi.url_scheme": "http",
        "HTTP_HOST": "board.example.test",
        "HTTP_X_FORWARDED_PROTO": "javascript",
    }

    assert public_base_url(environ) == "http://board.example.test"
