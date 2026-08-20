"""Public-path probe: does the address a human is actually given answer?

Every other liveness check in this estate asks whether a *process* is alive.
This one asks whether the *path* is, and the difference is the outage shape
that keeps recurring:

* 2026-08-11 — the arena served public 502s for hours. ``cloudflared`` was
  KeepAlive-supervised, so the tunnel stayed green and faithfully forwarded
  every request to an origin that was gone.
* 2026-08-19 — the staging approval queue had been healthy for weeks while
  its owner had never once seen it: every link he was handed pointed at a
  port with no listener. Nothing was down. Everything was unreachable.

So the artifact here is the response itself, fetched through the real front
door — ``Method.DESTINATION_PUBLIC``, "a 200 on a permalink is real evidence
from the destination".

The line this probe must never blur:

* a response we got and disliked (502, 404, wrong body) is a **FAULT** —
  that is evidence about the surface;
* a response we never got (timeout, DNS failure, refused) is
  **UNOBSERVABLE** — that is evidence about our own reachability.

Collapsing those two turns a dropped wifi connection into "the estate is
down", and a monitor that cries wolf about itself is a monitor that gets
muted. ``expect_substring`` exists because a parked page, a login wall and a
default nginx index all answer 200 cheerfully.
"""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from deadman.evidence.model import Evidence, Method, Observation, unobservable

#: Bounded so a hostile or bloated body cannot ride into the evidence batch,
#: whose delivery is size-capped at ingest.
_MAX_BODY_SNIPPET = 200

#: Read this many bytes at most; we only ever need a fingerprint of the body.
_MAX_READ_BYTES = 4096

_DEFAULT_TIMEOUT_S = 20.0


def _default_fetch(url: str, timeout: float):
    return urllib.request.urlopen(url, timeout=timeout)  # noqa: S310 — fixed config URL


@dataclass(frozen=True)
class PublicPathProbe:
    """Fetches a URL through its public address and rules on the response."""

    url: str
    surface_id: str
    expect_status: int = 200
    expect_substring: str | None = None
    timeout_s: float = _DEFAULT_TIMEOUT_S
    fetch: Callable[[str, float], object] = field(default=_default_fetch, repr=False)

    @property
    def surface(self) -> str:
        return self.surface_id

    @property
    def question(self) -> str:
        want = f"{self.expect_status}"
        if self.expect_substring:
            want += f" containing {self.expect_substring!r}"
        return f"does {self.url} answer {want} through its public address?"

    def observe(self) -> Evidence:
        started = time.monotonic()
        try:
            with self.fetch(self.url, self.timeout_s) as resp:  # type: ignore[union-attr]
                status = int(getattr(resp, "status", 0) or 0)
                body = resp.read(_MAX_READ_BYTES) or b""
        except Exception as exc:  # noqa: BLE001 — see module docstring
            # We did not learn the surface is broken. We learned we cannot
            # see it. Never a FAULT: an unreachable prober must not be able
            # to declare the estate down.
            return unobservable(
                self.surface_id,
                self.url,
                f"could not reach the path: {type(exc).__name__}: {exc}",
                error=type(exc).__name__,
            )

        latency_ms = round((time.monotonic() - started) * 1000)
        text = body.decode("utf-8", errors="replace")
        detail = {
            "status": status,
            "latency_ms": latency_ms,
            "body_snippet": text[:_MAX_BODY_SNIPPET],
        }

        if status != self.expect_status:
            return Evidence(
                surface=self.surface_id,
                observation=Observation.FAULT,
                method=Method.DESTINATION_PUBLIC,
                summary=(
                    f"{self.url} answered {status}, expected "
                    f"{self.expect_status} — the path a human is given is dead"
                ),
                source=self.url,
                detail=detail,
            )

        if self.expect_substring and self.expect_substring not in text:
            return Evidence(
                surface=self.surface_id,
                observation=Observation.FAULT,
                method=Method.DESTINATION_PUBLIC,
                summary=(
                    f"{self.url} answered {status} but the body lacks expected "
                    f"content {self.expect_substring!r} (parked page? login wall?)"
                ),
                source=self.url,
                detail={**detail, "expected_substring": self.expect_substring},
            )

        return Evidence(
            surface=self.surface_id,
            observation=Observation.HEALTHY,
            method=Method.DESTINATION_PUBLIC,
            summary=f"{self.url} answered {status} in {latency_ms}ms",
            source=self.url,
            detail=detail,
        )
