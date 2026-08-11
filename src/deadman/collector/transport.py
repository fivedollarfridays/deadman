"""What "unreachable" means to a collector, distinct from "answered badly".

Store-and-forward needs to tell these two facts apart. A service that is up
and returns a bad status has told the collector something real; a request
that never reached a server that could answer has told it nothing about the
batch at all. :class:`TransportError` names only the second case, so the
caller — :mod:`deadman.collector.run` — can spool on either without
conflating "the service said no" with "there was no service to ask".

The real implementation is stdlib ``urllib``, matching ``pyproject.toml``'s
``dependencies = []``: a collector needs no more of a network stack than the
one Python already ships.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

#: How long a collector waits for the ingest endpoint to answer before
#: giving up and treating the request as unreachable. A collector runs on a
#: schedule (DM2.6), so a hung connection must not hang the whole sweep.
DEFAULT_TIMEOUT_SECONDS = 10.0


class TransportError(Exception):
    """The request never reached a server that could return a status code.

    DNS failure, connection refused, timeout — all facts about the network,
    never about the batch.
    """


@runtime_checkable
class Transport(Protocol):
    """POSTs bytes somewhere and reports the status code.

    Raises :class:`TransportError` when it could not even ask; a non-2xx
    status the service *did* return is a plain ``int``, because deciding
    what that status means is the caller's job, not the transport's.
    """

    def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> int: ...


class UrllibTransport:
    """The real transport a deployed collector posts through."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout

    def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:
            # The service answered, just not with success. Reachable, so this
            # is a status for the caller to interpret, not a TransportError.
            return exc.code
        except urllib.error.URLError as exc:
            raise TransportError(f"could not reach {url}: {exc}") from exc
        except OSError as exc:
            raise TransportError(f"could not reach {url}: {exc}") from exc
