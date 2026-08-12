"""What a row's stored history says about it: how long it has held its
current state, and which collector reported it.

Split out of :mod:`deadman.service` rather than left inline: held-duration
and collector attribution are their own small piece of logic, independent of
the WSGI app that renders them, and keeping them in ``service.py`` alongside
everything else pushed that module past the architecture's per-file
function-count cap — the same reason
:mod:`deadman.verify.surface_verdict` was split out of
:mod:`deadman.verify.collector_liveness` earlier in the sprint.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from deadman.evidence.model import Evidence
from deadman.ingest.arrival import COLLECTOR_ID, RECEIVED_AT
from deadman.store.base import DEFAULT_HISTORY_LIMIT, EvidenceStore


def reported_by(evidence: Evidence) -> str | None:
    """Which collector reported this row, or ``None`` for the service's own
    probes.

    Gated on ``RECEIVED_AT`` rather than merely ``COLLECTOR_ID``: a liveness
    verdict the service derived itself (a collector's own liveness row, a
    surface judged ``stale`` or ``never reported``) also carries
    ``COLLECTOR_ID`` in its detail — naming which collector the row
    *concerns* — but only a row that actually crossed the wire through
    :func:`deadman.ingest.arrival.on_arrival` sets ``RECEIVED_AT``. Using that
    as the gate keeps this meaning "who told us this", not "who this is
    about".
    """
    if RECEIVED_AT not in evidence.detail:
        return None
    return evidence.detail.get(COLLECTOR_ID)


def held_since(evidence: Evidence, history: Sequence[Evidence]) -> datetime:
    """How far back ``history`` (oldest first) confirms ``evidence``'s current
    observation, walking backward from the newest entry until the state
    changes.

    Falls back to ``evidence.read_at`` — zero held duration — when ``history``
    is empty or its newest entry doesn't confirm the state being shown, so a
    surface with no persisted trail, or a verdict the service just derived,
    still renders a duration instead of raising or indexing into history that
    isn't there.
    """
    since = evidence.read_at
    for past in reversed(history):
        if past.observation != evidence.observation:
            break
        since = past.read_at
    return since


def history_for(store: EvidenceStore | None, surface: str) -> Sequence[Evidence]:
    """The bounded read behind held-duration. Never unbounded: capped at
    :data:`~deadman.store.base.DEFAULT_HISTORY_LIMIT` per surface per request,
    the same bound :mod:`deadman.verify.collector_liveness` already reads
    under.
    """
    if store is None:
        return ()
    return store.history(surface, limit=DEFAULT_HISTORY_LIMIT)
