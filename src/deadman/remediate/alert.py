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

**Transports, not just spellings.** A rail prefix is only as good as the name
somebody typed: the morning brief is ``cron:morning-brief`` and the alarm is
``email:...``, yet both go out through one SMTP account, and one expired
credential kills both. So the channel also carries its real ``identity``
(:func:`transport_identity`, e.g. ``smtp:<host>/<account>``), each monitored
surface may declare the transport it depends on, and the channel is refused
when the two are the same transport whatever either is called.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field


class AlertChannelInvalid(ValueError):
    """Raised at construction when the alert path is not out of band."""


def _rail(surface: str) -> str:
    """The transport family of a surface id: ``sms:relay`` -> ``sms``.

    Surface ids in this codebase are ``rail:identifier``. A bare string with
    no colon is its own rail, which keeps the comparison total rather than
    silently exempting anything that does not fit the convention.
    """
    return surface.split(":", 1)[0].strip().lower()


def transport_identity(kind: str, host: str, account: str) -> str:
    """The comparable identity of a real transport: ``kind:host/account``,
    trimmed and lower-cased so a difference in spelling is not a difference
    in transport."""
    return f"{kind}:{host}/{account}".strip().lower()


def same_transport(declared: str, identity: str) -> bool:
    """Whether a declared transport is ``identity``, compared the way
    :func:`transport_identity` normalises."""
    return declared.strip().lower() == identity.strip().lower()


@dataclass(frozen=True)
class AlertChannel:
    """A way to raise an alarm that does not depend on a watched surface."""

    transport: str
    """Surface-style id of the alerting path, e.g. ``email:ops@example.com``.
    Written in the same vocabulary as monitored surfaces precisely so the two
    can be compared."""

    send: Callable[[str], None]
    monitored: Sequence[str]
    identity: str = ""
    """The real transport the alarm sends over (:func:`transport_identity`).
    Empty only for callers with no real transport (the demo, tests)."""
    monitored_transports: Mapping[str, str] = field(default_factory=dict)
    """Monitored surface -> the transport it declares it depends on."""

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
        self._refuse_shared_transport()

    def _refuse_shared_transport(self) -> None:
        if not self.identity.strip():
            return
        for surface, declared in self.monitored_transports.items():
            if same_transport(declared, self.identity):
                raise AlertChannelInvalid(
                    f"alert transport {self.transport!r} is not out of band: it "
                    f"sends over the same transport the monitored surface "
                    f"{surface!r} declares it depends on. One failure of that "
                    f"transport (an expired credential, a locked account) "
                    f"silences the surface and its alarm together. Send the "
                    f"alarm over a transport no monitored surface uses."
                )

    def alert(self, message: str) -> None:
        """Raise the alarm. Failures propagate: a swallowed alert is silence."""
        self.send(message)
