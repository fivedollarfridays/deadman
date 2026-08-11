"""Metricool posting probe.

The surface with a real incident behind it. Metricool reported a scheduled
FWDAO roundtable post as published, the post never appeared, and nobody
noticed. So the question this probe asks is deliberately not the one the
scheduler answers:

    not "did Metricool say it published?" but "is the post at the
    destination?"

**The scheduler's report is the claim under test, never the evidence.** It is
``Method.REPORTED``, the weakest tier there is, and this module is built so
that no arrangement of scheduler confidence can produce ``HEALTHY``. That
verdict requires a read of the destination itself, at
``Method.DESTINATION_PUBLIC`` or better.

**Which destinations can be read is settled in**
:mod:`deadman.probes.destinations`, from the spike recorded in
``docs/metricool-verification.md``. The consequence lands here: an Instagram
post reported published yields ``UNOBSERVABLE`` forever, because an Instagram
permalink answers identically whether the post exists or not. That is a
declared blind spot, it gets its own line in every report via
``blind_spots()``, and it is strictly better than the fabricated pass that let
the original incident run unnoticed. The probe does not even fetch those
permalinks: there is nothing to learn from a response that cannot vary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from deadman.evidence.model import Evidence, Method, Observation, trust, unobservable
from deadman.probes.destinations import (
    MIN_TRUST_FOR_HEALTHY,
    DestinationReader,
    DestinationState,
    PermalinkReader,
    verification_method,
)

logger = logging.getLogger(__name__)

#: How far back to re-verify. Long enough to catch a miss across a weekend,
#: short enough that the probe is not re-fetching last month's calendar.
DEFAULT_WINDOW_HOURS = 48.0

#: A post reported published seconds ago may not have propagated yet, and
#: calling that absent manufactures a false FAULT. Recent posts are not
#: wrong, they are not yet due.
DEFAULT_GRACE_MINUTES = 10.0


@dataclass(frozen=True)
class ScheduledPost:
    """One post Metricool claims it published. A claim, not a fact."""

    post_id: str
    platform: str
    permalink: str | None
    reported_status: str
    reported_at: datetime


@runtime_checkable
class SchedulerClient(Protocol):
    """Metricool, or anything that reports what it believes it published."""

    def recently_published(self) -> list[ScheduledPost]: ...


@dataclass
class _Buckets:
    """Per-post outcomes for one sweep."""

    confirmed: list[str] = field(default_factory=list)
    absent: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    methods: list[Method] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    permalinks: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricoolProbe:
    """Asks whether every post Metricool reported published actually landed."""

    brand: str
    scheduler: SchedulerClient
    reader: DestinationReader = field(default_factory=PermalinkReader)
    window_hours: float = DEFAULT_WINDOW_HOURS
    grace_minutes: float = DEFAULT_GRACE_MINUTES

    @property
    def surface(self) -> str:
        return f"metricool:{self.brand}"

    @property
    def question(self) -> str:
        return (
            f"did every post Metricool reported published for {self.brand} in the "
            f"last {self.window_hours:g}h actually appear at its destination?"
        )

    def observe(self) -> Evidence:
        src = f"metricool:{self.brand} + destination permalink"
        due, pending = self._partition_by_time(self.scheduler.recently_published())

        if not due:
            return unobservable(
                self.surface,
                src,
                self._nothing_due_reason(pending),
                pending_grace_post_ids=pending,
                window_hours=self.window_hours,
            )

        return self._verdict(self._verify(due), pending, src)

    def _nothing_due_reason(self, pending: list[str]) -> str:
        if pending:
            return (
                f"{len(pending)} post(s) reported published but still inside the "
                f"{self.grace_minutes:g}m propagation grace period: nothing settled "
                f"enough to verify yet"
            )
        # Silence is not health. Whether the calendar should have had posts in
        # it is a different question, and this probe answers neither by guessing.
        return f"no posts reported published in the last {self.window_hours:g}h: nothing to verify"

    def _partition_by_time(
        self, posts: list[ScheduledPost]
    ) -> tuple[list[ScheduledPost], list[str]]:
        """Split into posts due for verification and posts still propagating.
        Anything older than the window is dropped: it was judged already."""
        now = datetime.now(timezone.utc)
        due: list[ScheduledPost] = []
        pending: list[str] = []

        for post in posts:
            age_hours = (now - post.reported_at).total_seconds() / 3600.0
            if age_hours < self.grace_minutes / 60.0:
                pending.append(post.post_id)
            elif age_hours <= self.window_hours:
                due.append(post)

        return due, pending

    def _verify(self, posts: list[ScheduledPost]) -> _Buckets:
        buckets = _Buckets()
        for post in posts:
            buckets.permalinks[post.post_id] = post.permalink
            self._classify(post, buckets)
        return buckets

    def _classify(self, post: ScheduledPost, buckets: _Buckets) -> None:
        """Sort one post into a bucket. Every path that is not a confirmed
        read of the destination lands in ``unverified``."""
        if verification_method(post.platform) is None:
            # Not fetched at all: on an opaque platform the response is the
            # same whether the post is there or not, so a request would buy
            # nothing but the appearance of diligence.
            buckets.unverified.append(post.post_id)
            buckets.reasons[post.post_id] = f"{post.platform} destination is not readable"
            return

        try:
            read = self.reader.read(post.platform, post.permalink)
        except Exception as exc:  # noqa: BLE001 — a broken instrument, not a fault
            logger.warning("reader raised for %s: %r", post.post_id, exc)
            buckets.unverified.append(post.post_id)
            buckets.reasons[post.post_id] = f"reader raised {type(exc).__name__}: {exc}"
            return

        if read.state is DestinationState.ABSENT:
            buckets.absent.append(post.post_id)
            buckets.methods.append(read.method)
        elif read.state is not DestinationState.PRESENT:
            buckets.unverified.append(post.post_id)
            buckets.reasons[post.post_id] = read.why or f"destination read was {read.state.value}"
        elif trust(read.method) < MIN_TRUST_FOR_HEALTHY:
            # "Present, according to a report" is the heartbeat this surface
            # already learned not to trust. Say so plainly in the report
            # rather than letting a weak tier pass as an observation.
            buckets.unverified.append(post.post_id)
            buckets.reasons[post.post_id] = (
                f"read claims present but via {read.method.value}, which is weaker than "
                f"{Method.DESTINATION_PUBLIC.value}: not destination evidence"
            )
        else:
            buckets.confirmed.append(post.post_id)
            buckets.methods.append(read.method)

    def _verdict(self, buckets: _Buckets, pending: list[str], src: str) -> Evidence:
        detail: dict[str, object] = {
            "confirmed_post_ids": buckets.confirmed,
            "absent_post_ids": buckets.absent,
            "unverified_post_ids": buckets.unverified,
            "pending_grace_post_ids": pending,
            "unverified_reasons": buckets.reasons,
            "window_hours": self.window_hours,
        }

        if buckets.absent:
            # A confirmed absence outranks blindness elsewhere: we did learn
            # this surface is broken. The blind siblings stay in the detail.
            return self._fault(buckets, detail, src)

        if buckets.unverified:
            checked = len(buckets.unverified) + len(buckets.confirmed)
            return unobservable(
                self.surface,
                src,
                f"{len(buckets.unverified)} of {checked} reported post(s) could not be "
                f"verified at the destination",
                **detail,
            )

        return Evidence(
            surface=self.surface,
            observation=Observation.HEALTHY,
            method=min(buckets.methods, key=trust),
            summary=(
                f"{len(buckets.confirmed)} post(s) confirmed present at the destination: "
                f"{', '.join(buckets.confirmed)}"
            ),
            source=src,
            detail=detail,
        )

    def _fault(self, buckets: _Buckets, detail: dict[str, object], src: str) -> Evidence:
        named = ", ".join(buckets.absent)
        detail["absent_permalinks"] = {i: buckets.permalinks.get(i) for i in buckets.absent}
        return Evidence(
            surface=self.surface,
            observation=Observation.FAULT,
            method=min(buckets.methods, key=trust, default=Method.DESTINATION_PUBLIC),
            summary=(
                f"{len(buckets.absent)} post(s) reported published by Metricool but "
                f"absent at the destination: {named}"
            ),
            source=src,
            detail=detail,
        )
