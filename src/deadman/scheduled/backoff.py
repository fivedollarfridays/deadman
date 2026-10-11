"""One incident pages a few times, on any instance: the durable repeat backoff.

From 2026-10-09 to 2026-10-11 one ongoing fault sent 39 alert emails in about
45 hours, roughly one an hour, and every one of them sat unread. An alarm that
repeats hourly teaches its owner to ignore the thread, which is the failure
this project exists to end. The throttle that allowed it was an hour long and
lived in instance memory, so a Cloud Run cold start also forgot it.

**Episodes.** An episode opens when a surface first alerts, or when its alert
state changes (``stale`` to ``fault`` is a new fact and is never suppressed).
The first alert of an episode always sends at once. While the episode stays
open in the same state, repeats follow :data:`BACKOFF_SCHEDULE`. A heal closes
the episode and sends exactly one recovery notice; a later fault is a new
episode and sends at once.

**The send record is durable, and it is the only memory there is.** What was
sent for a surface, and when, is one overwritten record in the evidence store
(:meth:`~deadman.store.base.EvidenceStore.load_alert_state`; on Firestore the
document ``alert_state/<surface key>``). :class:`DurableBackoffAlarm` holds no
state of its own and reads the record on every decision, so an instance that
booted a second ago decides exactly as one that has been warm for a week.

**"Is a repeat due and not yet sent", never "did a threshold fall in this
sweep".** The next repeat is due one schedule step after the last alert that
was actually sent. A sweep that arrives late therefore still sends it, once,
and the following step is measured from that late send, so a long gap is
never answered with a burst.

**The alert goes out before the record is written.** A send that raises
leaves the record untouched, so the next sweep tries again; the reverse order
would mark an alert as delivered that never left.

**An unreadable record means send.** If the record cannot be read or parsed
the alarm cannot know whether it already spoke, so it speaks: the alert is
sent, says in its body that repeats are not being limited, and the failure is
recorded as evidence on :data:`ALERT_STATE_FAILURE_SURFACE`. The one thing an
unreadable record never produces is a recovery notice, because "recovered"
mailed for every healthy surface on every sweep would be an alarm about
nothing; that failure is recorded as evidence instead.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from deadman.evidence.model import Evidence, Method, Observation
from deadman.remediate.alert import AlertChannel
from deadman.store.base import EvidenceStore, instant

#: How long after one alert the next repeat is due, while a surface stays in
#: the same alert state: 6 hours after the first alert, 12 hours after that,
#: then every 24 hours (the last step repeats). A fault held for 48 hours
#: therefore sends at 0 h, 6 h, 18 h and 42 h. This is the ops freshness
#: monitor's schedule, on purpose: one estate, one idea of "still broken".
BACKOFF_SCHEDULE: tuple[timedelta, ...] = (
    timedelta(hours=6),
    timedelta(hours=12),
    timedelta(hours=24),
)

#: Where a send record that could not be read or written is recorded. On the
#: ``alert`` rail beside ``alert:email``, so it can never collide with a
#: monitored surface or with the out-of-band check.
ALERT_STATE_FAILURE_SURFACE = "alert:send-record"

_SOURCE = "scheduled:backoff"


@dataclass(frozen=True)
class SendRecord:
    """What the alarm last sent for one surface."""

    state: str
    """The alert state the open episode is in (``fault``, ``stale``, ...)."""
    episode_started_at: datetime
    """When the first alert of this episode, in this state, was sent."""
    last_sent_at: datetime
    """When the newest alert of this episode was sent."""
    sends: int
    """How many alerts this episode has sent, the first included."""
    open: bool = True
    """False once the surface healed. A closed record is kept rather than
    deleted so "this surface has no open episode" is a read, not an absence
    that looks the same as a record that failed to save."""

    def to_document(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "episode_started_at": instant(self.episode_started_at).isoformat(),
            "last_sent_at": instant(self.last_sent_at).isoformat(),
            "sends": self.sends,
            "open": self.open,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> SendRecord:
        """Raises ``KeyError``, ``TypeError`` or ``ValueError`` for a record
        this code did not write; the caller treats that as unreadable."""
        sends, is_open = document["sends"], document["open"]
        if not isinstance(sends, int) or isinstance(sends, bool) or sends < 1:
            raise ValueError(f"sends must be a positive integer, got {sends!r}")
        if not isinstance(is_open, bool):
            raise ValueError(f"open must be a boolean, got {is_open!r}")
        return cls(
            state=str(document["state"]),
            episode_started_at=instant(datetime.fromisoformat(document["episode_started_at"])),
            last_sent_at=instant(datetime.fromisoformat(document["last_sent_at"])),
            sends=sends,
            open=is_open,
        )


def next_repeat_at(
    record: SendRecord, schedule: Sequence[timedelta] = BACKOFF_SCHEDULE
) -> datetime:
    """When the next repeat is due if the surface stays in this state."""
    return record.last_sent_at + schedule[min(record.sends, len(schedule)) - 1]


def span(duration: timedelta) -> str:
    """A duration a person reads at a glance: ``45m``, ``6h``, ``1d 18h``."""
    minutes = max(int(duration.total_seconds() // 60), 0)
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    parts = [f"{days}d" * bool(days), f"{hours}h" * bool(hours), f"{mins}m" * bool(mins)]
    return " ".join(part for part in parts if part) or "0m"


def stamp(moment: datetime) -> str:
    return instant(moment).strftime("%Y-%m-%d %H:%M UTC")


def compose(message: str, record: SendRecord, schedule: Sequence[timedelta]) -> str:
    """The alert body: the caller's line, then how long this has held and
    when the owner will hear again if nothing changes."""
    due = next_repeat_at(record, schedule)
    again = (
        f"If it does not heal, the next repeat is due {stamp(due)} "
        f"(in {span(due - record.last_sent_at)})."
    )
    if record.sends == 1:
        return f"{message}\n\nFirst alert for this state. {again}"
    held = span(record.last_sent_at - record.episode_started_at)
    return (
        f"{message}\n\nStill {record.state}: held for {held}, first alerted "
        f"{stamp(record.episode_started_at)}. This is repeat {record.sends - 1}. {again}"
    )


@dataclass
class DurableBackoffAlarm:
    """The production :class:`~deadman.scheduled.alerting.Alarm`. See the
    module docstring; holds no state between calls on purpose."""

    channel: AlertChannel
    store: EvidenceStore
    schedule: tuple[timedelta, ...] = BACKOFF_SCHEDULE

    def alert(self, key: str, state: str, message: str, *, now: datetime | None = None) -> None:
        """Send if this is a new episode, a changed state, or a due repeat."""
        moment = instant(now or datetime.now(timezone.utc))
        try:
            prior = self._load(key)
        except Exception as exc:  # noqa: BLE001 - any unreadable record means send
            self._alert_blind(key, state, message, moment, exc)
            return

        if prior is not None and prior.open and prior.state == state:
            if moment < next_repeat_at(prior, self.schedule):
                return
            record = replace(prior, last_sent_at=moment, sends=prior.sends + 1)
        else:
            record = SendRecord(state, moment, moment, sends=1)
        self.channel.alert(compose(message, record, self.schedule))
        self._save(key, record, moment)

    def recover(self, key: str, message: str, *, now: datetime | None = None) -> bool:
        """Close ``key``'s episode after a heal. Returns whether a recovery
        notice was sent.

        Only a surface with an open episode is notified, so a surface that
        never alerted sends nothing however many instances start cold. The
        episode is closed *before* the notice goes out: a re-fault after a
        heal is a new episode even if the notice itself fails to send.
        """
        moment = instant(now or datetime.now(timezone.utc))
        try:
            prior = self._load(key)
        except Exception as exc:  # noqa: BLE001 - recorded below, never swallowed
            self._record_failure(key, "read", exc, moment)
            self._save(key, SendRecord("unknown", moment, moment, sends=1, open=False), moment)
            return False
        if prior is None or not prior.open:
            return False
        self._save(key, replace(prior, open=False), moment)
        self.channel.alert(message)
        return True

    def _alert_blind(
        self, key: str, state: str, message: str, moment: datetime, exc: Exception
    ) -> None:
        """The send record is unreadable: send first, then say why on the
        record. The save that follows replaces a malformed record with a good
        one, so one bad document does not page on every sweep forever."""
        record = SendRecord(state, moment, moment, sends=1)
        self.channel.alert(
            f"{message}\n\nThe alarm could not read its own send record for {key} "
            f"({type(exc).__name__}), so it cannot tell whether this was already sent "
            f"and repeats are NOT being limited. Recorded as {ALERT_STATE_FAILURE_SURFACE}."
        )
        self._record_failure(key, "read", exc, moment)
        self._save(key, record, moment)

    def _load(self, key: str) -> SendRecord | None:
        document = self.store.load_alert_state(key)
        return None if document is None else SendRecord.from_document(document)

    def _save(self, key: str, record: SendRecord, moment: datetime) -> None:
        """A failed save is recorded and not raised: the alert already went
        out, and the cost of the lost record is a repeat that comes early,
        which is the loud direction to fail in."""
        try:
            self.store.save_alert_state(key, record.to_document())
        except Exception as exc:  # noqa: BLE001 - recorded as evidence
            self._record_failure(key, "written", exc, moment)

    def _record_failure(self, key: str, verb: str, exc: Exception, moment: datetime) -> None:
        operation = "read" if verb == "read" else "write"
        self.store.append(
            Evidence(
                surface=ALERT_STATE_FAILURE_SURFACE,
                observation=Observation.FAULT,
                method=Method.LOCAL_ARTIFACT,
                summary=(
                    f"alert send record for {key} could not be {verb}: {type(exc).__name__}: {exc}"
                ),
                source=_SOURCE,
                read_at=moment,
                detail={"key": key, "operation": operation, "error": str(exc)},
            )
        )
