"""The provenance rule: what a claim is worth once it has crossed a wire.

DM1 built a trust ladder because "the platform's API confirmed it" and "the
scheduler said so" are different claims about the world. DM2 puts a network
between the observer and the record, and that changes the grade of everything
that crosses it.

**The service did not see it; it was told.** A collector on the Mac reads a
send log and ships what it found. What Cloud Run then holds is not a local
artifact read — it holds a *report of* one, from a process it cannot inspect,
about a file it cannot open. Recording that as ``LOCAL_ARTIFACT`` would have
the service assert it inspected a disk it has no access to, which is a
heartbeat wearing a hat: the exact construction
:class:`~deadman.evidence.model.Method.REPORTED` exists to name.

So **arrival caps every method at ``REPORTED``**, and the cap is spelled as a
table rather than a one-liner so that adding a method to the ladder forces a
deliberate answer about what it becomes over a wire.
:func:`~deadman.ingest.arrival.arrival_method` is checked as total over
``Method`` and as never trust-increasing, and a test fails if the mapping is
ever replaced by the identity function.

**What that costs, stated plainly.** Every action floor in
:mod:`deadman.remediate.registry` sits above the 0.4 confidence ceiling that
:mod:`deadman.diagnose.grounding` imposes on a ``REPORTED`` citation. So a
diagnosis resting only on collected evidence escalates to a human instead of
moving infrastructure. That is not a side effect to be engineered around; it
is the correct reading of what the service actually knows. Acting on an
unverified relayed claim is how an automated remediation makes an outage
worse.

**The claim is downgraded, never erased.** The collector's own grade survives
in ``detail['reported_method']``, so a report can say "the collector claims a
local artifact read" and DM2.9 can write from what was actually asserted.

**Arrival metadata is not part of the observation's identity.** ``read_at`` is
when the surface was seen, ``received_at`` is when we heard about it, and
those are different facts — folding them together would date a spool delivered
after an outage as a burst of readings taken during it. Because our arrival
time differs on every delivery, a re-sent row hashes differently as a stored
row, so ``detail['wire_row_id']`` carries the identity of the *observation*
and is what :mod:`deadman.ingest.endpoint` deduplicates on.
"""

from __future__ import annotations

from datetime import datetime

from deadman.evidence.model import Evidence, Method
from deadman.store.base import instant, row_id

#: Detail key naming the collector that reported the row.
COLLECTOR_ID = "collector_id"

#: Detail key holding the service's own clock at delivery, ISO 8601 UTC.
#: Distinct from ``read_at``, which stays the collector's reading time.
RECEIVED_AT = "received_at"

#: Detail key preserving the grade the collector claimed, before the cap.
REPORTED_METHOD = "reported_method"

#: Detail key holding the content id of the row as it crossed the wire — the
#: observation's identity, independent of when we happened to receive it.
WIRE_ROW_ID = "wire_row_id"

#: What each claimed method becomes on arrival. Total over ``Method`` by test,
#: so a new member cannot be graded by a silent default.
ON_ARRIVAL: dict[Method, Method] = {
    Method.DESTINATION_API: Method.REPORTED,
    Method.DESTINATION_PUBLIC: Method.REPORTED,
    Method.LOCAL_ARTIFACT: Method.REPORTED,
    Method.ACTIVE_CANARY: Method.REPORTED,
    Method.REPORTED: Method.REPORTED,
}


def arrival_method(claimed: Method) -> Method:
    """The grade a claimed method earns once it has been relayed to us."""
    return ON_ARRIVAL[claimed]


def on_arrival(evidence: Evidence, collector_id: str, received_at: datetime) -> Evidence:
    """The stored form of a row a collector reported.

    Downgrades the method, annotates who said it and when we heard it, and
    leaves everything the collector observed — surface, observation, summary,
    source, ``read_at``, its own detail — untouched.

    ``source`` in particular is kept verbatim even though re-running it here
    would consult the wrong machine. It documents how the reading was actually
    made, and ``collector_id`` names where; rewriting it would lose the only
    record of the real instrument.
    """
    detail = dict(evidence.detail)
    detail[REPORTED_METHOD] = detail.get(REPORTED_METHOD, evidence.method.value)
    detail[WIRE_ROW_ID] = detail.get(WIRE_ROW_ID) or row_id(evidence)
    detail[COLLECTOR_ID] = collector_id
    detail[RECEIVED_AT] = instant(received_at).isoformat()
    return Evidence(
        surface=evidence.surface,
        observation=evidence.observation,
        method=arrival_method(evidence.method),
        summary=evidence.summary,
        source=evidence.source,
        read_at=evidence.read_at,
        detail=detail,
    )
