"""Out-of-band alerting.

**An alarm may not travel over anything deadman watches.** That is the entire
contract, and it is the nine-day outage stated as a rule. A sibling system's
morning brief was both the surface that died and the channel that would have
announced the death, so the failure concealed itself perfectly. Nobody was
ignoring an alert. There was no alert.

**The check happens at configuration time, not at send time.** By the time an
alert needs sending, the channel is exactly as likely to be down as the thing
being reported, and a runtime check would be discovering the problem at the
one moment it can no longer be acted on. Constructing an
:class:`AlertChannel` over a monitored rail raises immediately, at startup,
while somebody is still watching the logs.

**Rails, not just identifiers.** A transport is rejected when it matches a
monitored surface exactly *and* when it merely shares that surface's rail. If
``sms:relay`` is monitored, then ``sms:backup-number`` is not out of band: it
is the same physical path with a different destination, and it fails for the
same reason at the same moment.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


class AlertChannelInvalid(ValueError):
    """Raised at construction when the alert path is not out of band."""


def _rail(surface: str) -> str:
    """The transport family of a surface id: ``sms:relay`` -> ``sms``.

    Surface ids in this codebase are ``rail:identifier``. A bare string with
    no colon is its own rail, which keeps the comparison total rather than
    silently exempting anything that does not fit the convention.
    """
    return surface.split(":", 1)[0].strip().lower()


@dataclass(frozen=True)
class AlertChannel:
    """A way to raise an alarm that does not depend on a watched surface."""

    transport: str
    """Surface-style id of the alerting path, e.g. ``email:ops@example.com``.
    Written in the same vocabulary as monitored surfaces precisely so the two
    can be compared."""

    send: Callable[[str], None]
    monitored: Sequence[str]

    def __post_init__(self) -> None:
        rail = _rail(self.transport)
        for surface in self.monitored:
            if self.transport == surface or _rail(surface) == rail:
                raise AlertChannelInvalid(
                    f"alert transport {self.transport!r} is not out of band: it "
                    f"shares a rail with the monitored surface {surface!r}. If "
                    f"that surface fails, the alarm fails with it and the "
                    f"outage becomes self-concealing. Choose a transport on a "
                    f"rail deadman does not watch."
                )

    def alert(self, message: str) -> None:
        """Raise the alarm. Failures propagate: a swallowed alert is silence."""
        self.send(message)
