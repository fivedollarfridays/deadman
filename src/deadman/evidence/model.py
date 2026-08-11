"""The evidence model.

Two ideas carry this whole system.

**Absence is a state, not a null.** A surface that produced no signal has not
passed. It is unobserved, which is a blind state and strictly worse than a
known fault, because a known fault is at least known. Every place this
codebase could return ``None`` for "nothing came back", it returns
``Observation.UNOBSERVABLE`` instead, and callers cannot silently treat that
as healthy.

**How you learned something is part of what you learned.** "The platform's API
confirmed the post exists" and "the scheduler said it published" are different
claims about the world. Collapsing them into one boolean is how a monitor ends
up trusting a heartbeat. Every piece of evidence carries its ``Method``, and
each method has a trust tier that downstream reasoning can see.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Observation(str, Enum):
    """What a probe managed to determine. Three states, never two."""

    HEALTHY = "healthy"
    """Evidence was obtained and the surface is fine."""

    FAULT = "fault"
    """Evidence was obtained and the surface is broken."""

    UNOBSERVABLE = "unobservable"
    """No evidence could be obtained.

    This is NOT a verdict about the surface. It is a verdict about our ability
    to see it, and the two must never be conflated. A GMS returning 401 does
    not mean a dataset is stale; it means we are blind. Reporting blindness as
    a fault produces alarm storms, and reporting it as healthy produces the
    silent outage this project exists to catch.
    """


class Method(str, Enum):
    """How the evidence was obtained. Ordered by how much it can be trusted."""

    DESTINATION_API = "destination_api"
    """Asked the system of record directly. The post exists because the
    platform's own API says so. Highest trust."""

    DESTINATION_PUBLIC = "destination_public"
    """Fetched the artifact at its public address, no privileged access. A
    200 on a permalink is real evidence from the destination, just weaker
    than an authenticated read and more prone to bot walls."""

    LOCAL_ARTIFACT = "local_artifact"
    """Inspected something the process itself wrote: a send log row, an
    output file's mtime, free bytes on a volume."""

    ACTIVE_CANARY = "active_canary"
    """Manufactured the evidence by exercising the path end to end, because
    passive observation is ambiguous. Silence on the SMS relay means either
    no traffic or a dead rail; sending a canary and verifying it landed
    distinguishes them."""

    REPORTED = "reported"
    """A third party asserted it. The scheduler says it published. This is a
    heartbeat wearing a hat and it is the weakest tier there is. Never
    sufficient on its own to call a surface healthy."""


_TRUST_ORDER = [
    Method.REPORTED,
    Method.LOCAL_ARTIFACT,
    Method.ACTIVE_CANARY,
    Method.DESTINATION_PUBLIC,
    Method.DESTINATION_API,
]


def trust(method: Method) -> int:
    """Higher is more trustworthy. Lets reasoning prefer better evidence and
    lets a report say plainly that a verdict rests on a weak source."""
    return _TRUST_ORDER.index(method)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Evidence:
    """One thing we learned about one surface, and how we learned it.

    Immutable on purpose. Evidence is a record of an observation at a moment;
    nothing downstream may edit history to make a verdict tidier.
    """

    surface: str
    """Stable identifier, e.g. ``metricool:fwtx_dao`` or ``host:mac/disk``."""

    observation: Observation
    method: Method

    summary: str
    """One line a human can act on. Names the thing and the number."""

    source: str
    """The specific tool, endpoint or path consulted. Goes in the provenance
    table verbatim, so it must be precise enough to re-run by hand."""

    read_at: datetime = field(default_factory=_now)

    detail: dict[str, Any] = field(default_factory=dict)
    """Raw material for the diagnosis layer: status codes, error bodies, byte
    counts, timestamps. Unstructured on purpose, because reading messy
    heterogeneous failure evidence is precisely the model's job."""

    @property
    def is_blind(self) -> bool:
        return self.observation is Observation.UNOBSERVABLE

    @property
    def trust(self) -> int:
        return trust(self.method)

    def provenance_row(self) -> tuple[str, str, str, str]:
        """(source, method, surface, read_at) for the provenance table every
        report ends with. Facts are traceable or they are not facts."""
        return (
            self.source,
            self.method.value,
            self.surface,
            self.read_at.isoformat(),
        )


def unobservable(surface: str, source: str, why: str, **detail: Any) -> Evidence:
    """Build the blind-state record.

    Deliberately the most convenient constructor in this module. The failure
    mode being designed against is a tired engineer reaching for ``None``
    because it is easier than admitting the monitor cannot see.
    """
    return Evidence(
        surface=surface,
        observation=Observation.UNOBSERVABLE,
        method=Method.REPORTED,
        summary=f"cannot observe {surface}: {why}",
        source=source,
        detail={"reason": why, **detail},
    )
