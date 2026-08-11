"""Reading the destination platforms, and which ones can be read at all.

This module holds one thing: the findings of the destination-verification
spike (``docs/metricool-verification.md``) and the code that acts on them.
It is separate from any probe because verifiability is a property of the
platform, not of the surface that happens to publish there — the SMS relay's
canary verification will need the same knowledge.

**The finding that shapes everything here.** An Instagram permalink returns
HTTP 200 for a real public post *and* HTTP 200 for a shortcode that does not
exist, both carrying the same ``"pageID":"httpErrorPage"`` shell, under
browser and crawler user agents alike. Status carries no signal and neither
does the body. ``instagram_oembed`` returns the identical "Media Not Found"
for a real post without an approved Meta app, and that approval is
unavailable. Facebook returns 400 for everything, including real pages.

So those destinations are not "harder to verify", they are unreadable, and
the only honest thing to report about them is that we cannot see. X
permalinks do discriminate — 200 versus 404, stable across repeats, with the
post text in ``og:description`` — so X is readable at
``Method.DESTINATION_PUBLIC``.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from deadman.evidence.model import Method, trust

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0

#: Which destinations can actually be read, per the spike. ``None`` means
#: "this platform cannot be verified", which is a settled fact about someone
#: else's server and not a TODO.
PLATFORM_VERIFICATION: dict[str, Method | None] = {
    "x": Method.DESTINATION_PUBLIC,
    "twitter": Method.DESTINATION_PUBLIC,
    # Proven opaque: the same response for present and absent alike, so any
    # status mapping would be inventing evidence rather than gathering it.
    "instagram": None,
    "facebook": None,
    "threads": None,
    # A real activity URN was never tested and LinkedIn walls datacenter
    # traffic. Unproven is treated as unreadable until one fetch settles it.
    "linkedin": None,
}

#: Nothing weaker than a read of the destination may support ``HEALTHY``.
MIN_TRUST_FOR_HEALTHY = trust(Method.DESTINATION_PUBLIC)


def verification_method(platform: str) -> Method | None:
    """The evidence tier this platform's destination can support, or ``None``
    if it cannot be read. Unknown platforms fail closed to unreadable."""
    return PLATFORM_VERIFICATION.get(platform.strip().lower())


class DestinationState(str, Enum):
    """What a read of the destination established."""

    PRESENT = "present"
    """The artifact is at the destination. The scheduler told the truth."""

    ABSENT = "absent"
    """The destination was read and the artifact is not there. This is the
    incident: reported published, never appeared."""

    UNREADABLE = "unreadable"
    """The destination could not be read. Says nothing about the artifact."""


@dataclass(frozen=True)
class DestinationRead:
    """The outcome of looking at a destination, and how we looked.

    ``method`` travels with the result rather than being assumed by the
    caller, so a reader cannot quietly upgrade its own evidence tier: the
    probe checks it before letting a ``PRESENT`` count toward ``HEALTHY``.
    """

    state: DestinationState
    method: Method
    detail: dict[str, object] = field(default_factory=dict)
    why: str = ""


@runtime_checkable
class DestinationReader(Protocol):
    """Reads a platform. Reports a read; never reaches a verdict."""

    def read(self, platform: str, permalink: str | None) -> DestinationRead: ...


Fetch = Callable[[str], tuple[int, str]]


def urllib_fetch(url: str) -> tuple[int, str]:
    """Default transport, returning ``(status, body)``. Injected in tests, so
    the suite never opens a socket."""
    request = urllib.request.Request(url, headers={"User-Agent": "deadman/0.1 (+probe)"})
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:  # a status is still a reading
        return exc.code, ""


@dataclass(frozen=True)
class PermalinkReader:
    """Fetches an artifact at its public address.

    Refuses to fetch platforms the spike proved opaque, even though callers
    are expected to skip them anyway. On Instagram, mapping ``200 -> PRESENT``
    manufactures exactly the false ``HEALTHY`` this project exists to catch,
    so the guard lives at the point of the fetch rather than depending on
    every future caller remembering the finding.
    """

    fetch: Fetch = urllib_fetch

    def read(self, platform: str, permalink: str | None) -> DestinationRead:
        if verification_method(platform) is None:
            return self._unreadable(
                f"{platform} destinations are not readable "
                f"(see docs/metricool-verification.md)",
                platform=platform,
            )
        if not permalink:
            return self._unreadable("no permalink to read")

        try:
            status, body = self.fetch(permalink)
        except Exception as exc:  # noqa: BLE001 — transport failure is blindness
            logger.warning("permalink fetch failed for %s: %r", permalink, exc)
            return self._unreadable(f"fetch raised {type(exc).__name__}: {exc}")

        return self._from_status(status, body, platform)

    @staticmethod
    def _from_status(status: int, body: str, platform: str) -> DestinationRead:
        method = PLATFORM_VERIFICATION[platform.strip().lower()]
        assert method is not None  # guarded by read(); keeps the type honest
        detail: dict[str, object] = {"http_status": status, "body_bytes": len(body)}

        if status == 200:
            return DestinationRead(DestinationState.PRESENT, method, detail)
        if status in (404, 410):
            return DestinationRead(DestinationState.ABSENT, method, detail)
        # 403, 429, 5xx, and a 0 from a transport that never connected all
        # mean the same thing: no answer was given about the artifact.
        return DestinationRead(
            DestinationState.UNREADABLE,
            method,
            detail,
            why=f"destination returned {status}, which is not an answer about the post",
        )

    @staticmethod
    def _unreadable(why: str, **detail: object) -> DestinationRead:
        return DestinationRead(DestinationState.UNREADABLE, Method.REPORTED, dict(detail), why=why)
