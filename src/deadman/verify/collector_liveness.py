"""Is anyone still reporting, and is what they reported still true.

DM1 argued that a surface producing no signal has not passed. DM2 puts a
network between the observer and the record, which raises the same argument
one level up and makes it worse: a healthy estate and a dead collector deliver
the identical empty inbox, and an inbox is exactly what the board reads. This
module is the reason those two cannot look the same.

**Two clocks, because there are two questions.** A collector's liveness is
about *delivery* and is timed by ``received_at``; a surface's freshness is
about *reading* and is timed by ``read_at``. Store-and-forward makes the
difference real rather than pedantic: a collector that lost the network for a
day and then drained its spool is alive — it just shipped — while every
reading in that spool is a day old. The honest board says both, and it can
only say both because :mod:`deadman.ingest.arrival` recorded when we heard
separately from when it was seen. Timing freshness by arrival would let a
collector refresh the whole board by re-sending yesterday.

**Three states for a collector, for the same reason there are three for a
surface.** :class:`~deadman.self_check.Liveness` is reused deliberately rather
than reinvented here: "it stopped" and "it never started, or it is posting to
the wrong URL" are different mornings, and DM1.11 already named them ``STALE``
and ``NO_EVIDENCE``. One vocabulary, whether the thing being checked is
deadman's own sweep or a collector on a laptop.

**Both silences are a FAULT, and the distinction survives anyway.** Non-live
means a fault row naming the collector, not a missing row — a quiet board is
the failure being designed against, so silence has to be loud. Which silence
it is lives in ``detail['liveness']`` and in the summary, exactly as DM1.11
exits non-zero for both states while keeping them apart in the result.

**A stale surface reads UNOBSERVABLE, whatever it last said.** Including when
it last said FAULT. That is not losing an alarm: blindness is itself alarming
and counted, the collector is faulting beside it, and the previous observation
is carried in ``detail['last_observation']`` rather than discarded. What is
refused is asserting a *current* verdict from a reading that is too old to be
one — in either direction.

**The store is the only thing read here.** No path, no log, no local file: an
:class:`~deadman.store.base.EvidenceStore` in, evidence out. That is what lets
liveness run on Cloud Run, where the surfaces themselves are unreachable by
construction.

The one honest limit: arrivals are searched through the newest
:data:`ARRIVAL_LOOKBACK` rows per surface, ordered by ``read_at``. A collector
that drains a spool older than that many newer readings can have its delivery
missed, which reads as silence — an alarm, never a false green.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from deadman.evidence.model import Evidence, Method, Observation, unobservable
from deadman.ingest.arrival import COLLECTOR_ID, RECEIVED_AT
from deadman.self_check import Liveness
from deadman.store.base import DEFAULT_HISTORY_LIMIT, EvidenceStore, instant
from deadman.verify.expectations import CollectorExpectation

#: Named in the ``source`` of every row this module derives, so a board reader
#: can tell a verdict deadman computed from a reading somebody delivered.
SOURCE = "verify:collector_liveness"

#: Surface ids for collectors themselves: ``collector:kevin-mac``. The same
#: ``rail:identifier`` shape every other surface uses, which is what lets an
#: alerting channel be checked against them (:mod:`deadman.remediate.alert`).
COLLECTOR_RAIL = "collector"

#: How many rows per surface are searched for a delivery. See the module
#: docstring for what a spool older than this does, and does not, do.
ARRIVAL_LOOKBACK = DEFAULT_HISTORY_LIMIT

LIVENESS = "liveness"
CADENCE_SECONDS = "cadence_seconds"
SILENT_AFTER_SECONDS = "silent_after_seconds"
LAST_REPORT_AT = "last_report_at"
SILENT_FOR_SECONDS = "silent_for_seconds"
LAST_OBSERVATION = "last_observation"
LAST_READ_AT = "last_read_at"
AGE_SECONDS = "age_seconds"
DECLARED_SURFACES = "declared_surfaces"

_FRESH = "fresh"
_STALE = "stale"
_UNREPORTED = "unreported"


def collector_surface(collector_id: str) -> str:
    """The surface id a collector's own liveness is reported under."""
    return f"{COLLECTOR_RAIL}:{collector_id}"


@dataclass(frozen=True)
class CollectorReport:
    """Whether one collector is still delivering, and when it last did."""

    expectation: CollectorExpectation
    liveness: Liveness
    last_report_at: datetime | None
    silent_for_seconds: float | None
    checked_at: datetime


@dataclass(frozen=True)
class LivenessReport:
    """The board's liveness half: rows to show, and counts that stay apart.

    ``fresh``, ``stale`` and ``unreported`` partition the declared surfaces.
    Keeping ``unreported`` out of every other count is the point: "no faults"
    and "nothing reported" are different states of the world that a single
    number has no way to distinguish.
    """

    collectors: tuple[Evidence, ...]
    surfaces: tuple[Evidence, ...]
    fresh: int
    stale: int
    unreported: int
    undeclared: tuple[str, ...]
    """Surfaces the store holds evidence for that no collector declares. Shown
    rather than dropped — evidence arriving for an undeclared surface is a
    configuration gap — but not judged, because nothing declared a cadence to
    judge it against."""

    @property
    def rows(self) -> tuple[Evidence, ...]:
        """Everything liveness contributes to the board, collectors first."""
        return self.collectors + self.surfaces


def assess(
    store: EvidenceStore,
    expectations: Iterable[CollectorExpectation],
    now: datetime | None = None,
) -> LivenessReport:
    """Reconcile what should have been reported against what the store holds."""
    moment = instant(now if now is not None else _now())
    declared_by = tuple(expectations)
    collectors = tuple(
        collector_evidence(assess_collector(store, expectation, moment))
        for expectation in declared_by
    )

    latest = store.latest_per_surface()
    judged = [
        _judge_surface(surface, latest.get(surface), expectation, moment)
        for expectation in declared_by
        for surface in expectation.surfaces
    ]
    kinds = [kind for kind, _ in judged]
    declared = {surface for e in declared_by for surface in e.surfaces}

    return LivenessReport(
        collectors=collectors,
        surfaces=tuple(row for _, row in judged),
        fresh=kinds.count(_FRESH),
        stale=kinds.count(_STALE),
        unreported=kinds.count(_UNREPORTED),
        undeclared=tuple(sorted(set(latest) - declared)),
    )


def assess_collector(
    store: EvidenceStore, expectation: CollectorExpectation, now: datetime | None = None
) -> CollectorReport:
    """Has this collector delivered anything inside its declared window."""
    moment = instant(now if now is not None else _now())
    last = _last_arrival(store, expectation)
    if last is None:
        return CollectorReport(expectation, Liveness.NO_EVIDENCE, None, None, moment)

    silent = (moment - last).total_seconds()
    liveness = Liveness.STALE if silent > expectation.silence_after_seconds else Liveness.LIVE
    return CollectorReport(expectation, liveness, last, silent, moment)


def collector_evidence(report: CollectorReport) -> Evidence:
    """A collector's liveness as a board row.

    ``LOCAL_ARTIFACT``, and that is not a slip: the service is not relaying
    somebody's claim here, it is reporting what its own store does and does
    not contain. Whether a delivery arrived is the one fact about the estate
    the service knows first-hand.
    """
    expectation = report.expectation
    detail: dict[str, object] = {
        LIVENESS: report.liveness.value,
        COLLECTOR_ID: expectation.collector_id,
        CADENCE_SECONDS: expectation.interval_seconds,
        SILENT_AFTER_SECONDS: expectation.silence_after_seconds,
        DECLARED_SURFACES: list(expectation.surfaces),
    }
    if report.last_report_at is not None:
        detail[LAST_REPORT_AT] = report.last_report_at.isoformat()
        detail[SILENT_FOR_SECONDS] = round(report.silent_for_seconds or 0.0, 1)

    return Evidence(
        surface=collector_surface(expectation.collector_id),
        observation=(
            Observation.HEALTHY if report.liveness is Liveness.LIVE else Observation.FAULT
        ),
        method=Method.LOCAL_ARTIFACT,
        summary=_collector_summary(report),
        source=SOURCE,
        read_at=report.checked_at,
        detail=detail,
    )


def _collector_summary(report: CollectorReport) -> str:
    expectation = report.expectation
    if report.liveness is Liveness.NO_EVIDENCE:
        return (
            f"collector {expectation.collector_id} has never reported; it is expected "
            f"every {expectation.interval_seconds:g}s"
        )
    silent = report.silent_for_seconds or 0.0
    deadline = expectation.silence_after_seconds
    if report.liveness is Liveness.STALE:
        return (
            f"collector {expectation.collector_id} has not reported for {silent:.0f}s, "
            f"past its declared {deadline:g}s deadline"
        )
    return (
        f"collector {expectation.collector_id} last reported {silent:.0f}s ago, inside "
        f"its declared {deadline:g}s deadline"
    )


def _judge_surface(
    surface: str,
    stored: Evidence | None,
    expectation: CollectorExpectation,
    moment: datetime,
) -> tuple[str, Evidence]:
    """One declared surface: never reported, stale, or the stored row as-is."""
    if stored is None:
        return _UNREPORTED, _never_reported(surface, expectation)

    age = (moment - instant(stored.read_at)).total_seconds()
    if age > expectation.silence_after_seconds:
        return _STALE, _too_old(stored, expectation, age)
    return _FRESH, stored


def _never_reported(surface: str, expectation: CollectorExpectation) -> Evidence:
    return unobservable(
        surface=surface,
        source=SOURCE,
        why=(
            f"no evidence has ever arrived for {surface}; collector "
            f"{expectation.collector_id} is expected to report it every "
            f"{expectation.interval_seconds:g}s"
        ),
        **_cadence_detail(expectation, Liveness.NO_EVIDENCE),
    )


def _too_old(stored: Evidence, expectation: CollectorExpectation, age: float) -> Evidence:
    return unobservable(
        surface=stored.surface,
        source=SOURCE,
        why=(
            f"the newest evidence for {stored.surface} was read {age:.0f}s ago, past the "
            f"{expectation.silence_after_seconds:g}s allowed by its declared "
            f"{expectation.interval_seconds:g}s cadence"
        ),
        **_cadence_detail(expectation, Liveness.STALE),
        **{
            LAST_OBSERVATION: stored.observation.value,
            LAST_READ_AT: instant(stored.read_at).isoformat(),
            AGE_SECONDS: round(age, 1),
        },
    )


def _cadence_detail(expectation: CollectorExpectation, liveness: Liveness) -> dict[str, object]:
    """What every derived row carries, so a reader can check the arithmetic."""
    return {
        LIVENESS: liveness.value,
        COLLECTOR_ID: expectation.collector_id,
        CADENCE_SECONDS: expectation.interval_seconds,
        SILENT_AFTER_SECONDS: expectation.silence_after_seconds,
    }


def _last_arrival(store: EvidenceStore, expectation: CollectorExpectation) -> datetime | None:
    """When this collector last delivered anything, by our clock."""
    stamps = [
        stamp
        for surface in expectation.surfaces
        for stamp in _arrival_stamps(
            store.history(surface, limit=ARRIVAL_LOOKBACK), expectation.collector_id
        )
    ]
    return max(stamps, default=None)


def _arrival_stamps(rows: Sequence[Evidence], collector_id: str) -> Iterator[datetime]:
    """Delivery times of rows *this* collector actually sent us.

    Two filters, both load-bearing. A row another collector reported says
    nothing about this one — otherwise a dead collector hides behind a working
    one that happens to report the same surface. And a row with no
    ``received_at`` never crossed the wire at all; treating its ``read_at`` as
    a delivery would let the service's own writes forge a heartbeat.
    """
    for row in rows:
        if row.detail.get(COLLECTOR_ID) != collector_id:
            continue
        stamp = _parse_stamp(row.detail.get(RECEIVED_AT))
        if stamp is not None:
            yield stamp


def _parse_stamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return instant(datetime.fromisoformat(value))
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)
