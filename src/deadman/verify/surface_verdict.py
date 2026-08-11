"""One declared surface, judged: fresh, stale, or never reported.

Split out of :mod:`deadman.verify.collector_liveness`, which had grown two
jobs. That module answers "is this *collector* delivering"; this one answers
"what does the newest row for this *surface* entitle us to say", and the two
questions have different inputs and different failure modes. The seam is also
where the sharpest bug in the sprint lived, so it is worth being able to read
on its own.

**Every derived row here is ``UNOBSERVABLE``, never ``FAULT``.** A surface we
have not heard about is a statement about our own blindness, not about the
surface's condition, and collapsing the two is the specific confusion this
project exists to prevent.
"""

from __future__ import annotations

from datetime import datetime

from deadman.evidence.model import Evidence, unobservable
from deadman.ingest.arrival import COLLECTOR_ID
from deadman.self_check import Liveness
from deadman.store.base import instant
from deadman.verify.expectations import CollectorExpectation

#: Named in the ``source`` of every row derived here and in
#: :mod:`deadman.verify.collector_liveness`, so a board reader can tell a
#: verdict deadman computed from a reading somebody delivered.
SOURCE = "verify:collector_liveness"

LIVENESS = "liveness"
CADENCE_SECONDS = "cadence_seconds"
SILENT_AFTER_SECONDS = "silent_after_seconds"
LAST_OBSERVATION = "last_observation"
LAST_READ_AT = "last_read_at"
AGE_SECONDS = "age_seconds"
READ_AT_AHEAD_SECONDS = "read_at_ahead_seconds"
REPORTED_READ_AT = "reported_read_at"

FRESH = "fresh"
STALE = "stale"
UNREPORTED = "unreported"


def judge_surface(
    surface: str,
    stored: Evidence | None,
    expectation: CollectorExpectation,
    moment: datetime,
) -> tuple[str, Evidence]:
    """One declared surface: never reported, stale, or the stored row as-is."""
    if stored is None:
        return UNREPORTED, never_reported(surface, expectation)

    age = (moment - instant(stored.read_at)).total_seconds()
    if age < 0:
        return STALE, from_the_future(stored, -age)
    if age > expectation.silence_after_seconds:
        return STALE, too_old(stored, expectation, age)
    return FRESH, stored


def from_the_future(stored: Evidence, ahead: float) -> Evidence:
    """A row whose ``read_at`` is ahead of our clock says nothing about now.

    :mod:`deadman.ingest.wire` refuses these at the door, so reaching this
    branch means the row predates that guard or arrived by another path. It is
    judged here too because the failure is silent and permanent: a negative age
    never exceeds the silence window, so the row would read fresh forever, and
    the store orders by ``read_at``, so it would also stay newest forever.
    Treating it as blindness rather than health is the whole argument of this
    project applied to our own data.
    """
    return unobservable(
        surface=stored.surface,
        source=SOURCE,
        why=(
            f"{stored.surface} has a reading {int(ahead)}s in the future, so its "
            "freshness cannot be judged; suspect a skewed clock on the reporting collector"
        ),
        **{
            READ_AT_AHEAD_SECONDS: ahead,
            REPORTED_READ_AT: instant(stored.read_at).isoformat(),
        },
    )


def never_reported(surface: str, expectation: CollectorExpectation) -> Evidence:
    return unobservable(
        surface=surface,
        source=SOURCE,
        why=(
            f"no evidence has ever arrived for {surface}; collector "
            f"{expectation.collector_id} is expected to report it every "
            f"{expectation.interval_seconds:g}s"
        ),
        **cadence_detail(expectation, Liveness.NO_EVIDENCE),
    )


def too_old(stored: Evidence, expectation: CollectorExpectation, age: float) -> Evidence:
    return unobservable(
        surface=stored.surface,
        source=SOURCE,
        why=(
            f"the newest evidence for {stored.surface} was read {age:.0f}s ago, past the "
            f"{expectation.silence_after_seconds:g}s allowed by its declared "
            f"{expectation.interval_seconds:g}s cadence"
        ),
        **cadence_detail(expectation, Liveness.STALE),
        **{
            LAST_OBSERVATION: stored.observation.value,
            LAST_READ_AT: instant(stored.read_at).isoformat(),
            AGE_SECONDS: round(age, 1),
        },
    )


def cadence_detail(expectation: CollectorExpectation, liveness: Liveness) -> dict[str, object]:
    """What every derived row carries, so a reader can check the arithmetic."""
    return {
        LIVENESS: liveness.value,
        COLLECTOR_ID: expectation.collector_id,
        CADENCE_SECONDS: expectation.interval_seconds,
        SILENT_AFTER_SECONDS: expectation.silence_after_seconds,
    }
