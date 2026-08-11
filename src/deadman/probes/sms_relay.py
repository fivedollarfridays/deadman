"""Phone/SMS relay probe with an active canary.

The surface where passive observation is genuinely ambiguous. No traffic and
a dead rail produce the identical signal: silence. A probe that infers
health from quiet would call a severed relay healthy for as long as nobody
happens to text through it, which is exactly the failure mode this project
exists to catch. So this probe never listens passively. It manufactures its
own evidence by sending a canary and checking whether the canary landed.

**Dispatch acceptance is not delivery.** A relay that acknowledges a send
request has made a claim, not proved one — the same trap
:mod:`deadman.probes.metricool` is built against, where the scheduler's own
report is ``Method.REPORTED`` and never sufficient for ``HEALTHY``. Here the
claim under test is the relay's dispatch acknowledgement, and the only
evidence that outranks it is a read of the destination's own sent folder.

**Unreachable is not rejected.** Failing to reach the relay host at all
tells us nothing about the relay — it could be our network, DNS, or a
transient blip — so it degrades to ``UNOBSERVABLE``, the same as any other
broken instrument (see :mod:`deadman.probes.base`). A host that answers and
explicitly refuses the send (bad auth, invalid destination, quota) has told
us something real about the relay, so that is ``FAULT``. Collapsing the two
into one "send failed" bucket would blind an operator to the difference
between "check your network" and "the relay is actually broken".

**Cadence exists because canaries are not free.** Real SMS sends cost money
and can trip carrier rate limits, so this probe does not fire on every
sweep. It records each attempt and only sends a fresh canary once the
configured cadence has elapsed. Silence inside that window is not evidence
of anything — see ``_last_sent_at`` — and reporting it as ``HEALTHY`` would
reintroduce the exact ambiguity the canary exists to resolve. It stays
``UNOBSERVABLE`` until a new canary actually runs.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from deadman.evidence.model import Evidence, Method, Observation, unobservable

logger = logging.getLogger(__name__)

SURFACE = "sms:relay"

#: Conservative on purpose: canaries are real sends against a real carrier,
#: so the default favours cost and rate-limit safety over catching a dead
#: rail within the hour. Twice a day is enough to bound the blind window
#: without hammering the relay.
DEFAULT_CADENCE_HOURS = 12.0


class DispatchOutcome(str, Enum):
    """What the relay did with the canary at dispatch time. Never the whole
    story — see the module docstring on why acceptance is not delivery."""

    ACCEPTED = "accepted"
    """The relay took the send. Not proof it arrived anywhere."""

    UNREACHABLE = "unreachable"
    """Could not reach the relay host at all. Says nothing about the relay
    itself, only about our ability to test it right now."""

    REJECTED = "rejected"
    """The relay host answered and explicitly refused the send. Real
    evidence the relay is broken."""


@dataclass(frozen=True)
class DispatchResult:
    """The outcome of handing a canary to the relay, and why."""

    outcome: DispatchOutcome
    detail: dict[str, object] = field(default_factory=dict)
    why: str = ""


@runtime_checkable
class RelayClient(Protocol):
    """The phone/SMS relay, or a fake standing in for it in tests."""

    def send_canary(self, token: str) -> DispatchResult: ...


@runtime_checkable
class SentFolderReader(Protocol):
    """Reads the destination's sent folder. The only place a canary can be
    confirmed, because dispatch acceptance is not delivery."""

    def find(self, token: str) -> bool: ...


def _new_token() -> str:
    return f"canary-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class SmsRelayProbe:
    """Sends an active canary through the relay and verifies it landed."""

    relay: RelayClient
    sent_folder: SentFolderReader
    history_path: Path = Path("sms-canary-history.jsonl")
    cadence_hours: float = DEFAULT_CADENCE_HOURS
    token_factory: Callable[[], str] = field(default=_new_token)

    @property
    def surface(self) -> str:
        return SURFACE

    @property
    def question(self) -> str:
        return (
            f"did an active canary sent within the last {self.cadence_hours:g}h "
            f"land in the relay's sent folder?"
        )

    def observe(self) -> Evidence:
        src = "sms:relay active canary"
        now = datetime.now(timezone.utc)
        last_sent_at = self._last_sent_at()

        if last_sent_at is not None:
            age_hours = (now - last_sent_at).total_seconds() / 3600.0
            if age_hours < self.cadence_hours:
                return unobservable(
                    SURFACE,
                    src,
                    f"no canary due yet: last one sent {age_hours:.1f}h ago, "
                    f"cadence is {self.cadence_hours:g}h",
                    last_canary_at=last_sent_at.isoformat(),
                    cadence_hours=self.cadence_hours,
                )

        return self._run_canary(src, now)

    def _run_canary(self, src: str, now: datetime) -> Evidence:
        token = self.token_factory()

        try:
            dispatch = self.relay.send_canary(token)
        except Exception as exc:  # noqa: BLE001 -- a broken instrument, not a fault
            logger.warning("relay raised dispatching canary %s: %r", token, exc)
            return unobservable(
                SURFACE, src, f"relay raised {type(exc).__name__}: {exc}", token=token
            )

        # Recorded even on an unreachable/rejected outcome: cadence throttles
        # *attempts*, not just successes, or a persistently broken relay
        # would be hammered every sweep forever.
        self._record(now, token)

        if dispatch.outcome is DispatchOutcome.UNREACHABLE:
            return unobservable(
                SURFACE,
                src,
                f"relay host unreachable: {dispatch.why}",
                token=token,
                dispatch_outcome=dispatch.outcome.value,
                **dispatch.detail,
            )

        if dispatch.outcome is DispatchOutcome.REJECTED:
            return Evidence(
                surface=SURFACE,
                observation=Observation.FAULT,
                method=Method.ACTIVE_CANARY,
                summary=f"canary {token} rejected by relay: {dispatch.why}",
                source=src,
                detail={
                    "token": token,
                    "dispatch_outcome": dispatch.outcome.value,
                    **dispatch.detail,
                },
            )

        return self._verify_landing(token, dispatch, src)

    def _verify_landing(self, token: str, dispatch: DispatchResult, src: str) -> Evidence:
        detail = {"token": token, "dispatch_outcome": dispatch.outcome.value, **dispatch.detail}

        try:
            landed = self.sent_folder.find(token)
        except Exception as exc:  # noqa: BLE001 -- a broken instrument, not a fault
            logger.warning("sent-folder read raised for %s: %r", token, exc)
            return unobservable(
                SURFACE, src, f"sent-folder read raised {type(exc).__name__}: {exc}", **detail
            )

        if landed:
            return Evidence(
                surface=SURFACE,
                observation=Observation.HEALTHY,
                method=Method.ACTIVE_CANARY,
                summary=f"canary {token} confirmed in the sent folder",
                source=src,
                detail=detail,
            )

        return Evidence(
            surface=SURFACE,
            observation=Observation.FAULT,
            method=Method.ACTIVE_CANARY,
            summary=(
                f"canary {token} accepted by the relay but never appeared in the sent "
                f"folder: dead rail"
            ),
            source=src,
            detail=detail,
        )

    def _last_sent_at(self) -> datetime | None:
        try:
            lines = [ln for ln in self.history_path.read_text().splitlines() if ln.strip()]
        except OSError:
            return None

        for line in reversed(lines):
            try:
                row = json.loads(line)
                ts = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00"))
            except (ValueError, TypeError, KeyError):
                continue  # a torn row loses one attempt, not the whole history
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        return None

    def _record(self, when: datetime, token: str) -> None:
        """Append one attempt. Best effort: failing to extend the history
        must never prevent reporting the canary result we already have."""
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("a") as fh:
                fh.write(json.dumps({"ts": when.isoformat(), "token": token}) + "\n")
        except OSError:
            pass
