"""The shipped actions, and the causes deliberately left without one.

Three functions, each a handful of lines, each doing one thing through an
injected capability. That is the whole of what this system is permitted to do
to anyone's infrastructure, and it is short enough to read in one sitting on
purpose — the list of things an agent can do to production should fit on a
screen.

What is *not* here is as much of the design as what is.

``POLICY_REJECTION``
    The platform read the artifact and refused it. Re-queueing burns rate
    limit against a decision already made, and no code in this repo can edit a
    caption. It escalates to a human, which is the correct outcome rather than
    a gap.

``CHANNEL_DISCONNECTED``
    Re-sending to a destination that is no longer wired up succeeds locally
    and delivers nothing — precisely the false pass this project exists to
    catch. Reconnecting is an interactive OAuth flow, not an action.

``UNKNOWN``
    By definition the failure was not recognised. Anything registered here
    would be the guess the design forbids.

None of these three return a value that could be mistaken for a fix. See
:class:`~deadman.remediate.registry.ActionResult` — ``performed`` says the code
ran, and DM1.7's verification loop is what says the surface recovered.
"""

from __future__ import annotations

from deadman.evidence.model import Evidence
from deadman.remediate.cause import Cause, causes_in
from deadman.remediate.registry import (
    Action,
    ActionContext,
    ActionResult,
    Registry,
)

RETRY_NOW = "retry-now"
REFRESH_CREDENTIAL = "refresh-credential"
RECLAIM_SPACE = "reclaim-space"


def _target(context: ActionContext) -> Evidence:
    """The cited evidence that actually carries the cause being acted on.

    A diagnosis usually cites the fault *and* the reason for it — the post is
    absent, and here is the 503 behind it. The action belongs on the row that
    established the cause, not on whichever row happened to be cited first.
    """
    for evidence in context.evidence:
        if context.cause in causes_in(evidence):
            return evidence
    return context.evidence[0]


def retry_now(context: ActionContext) -> ActionResult:
    """Re-submit immediately. Correct only because the cause is transient."""
    surface = _target(context).surface
    accepted = context.capabilities.requeue(surface)
    return ActionResult(
        action=RETRY_NOW,
        performed=True,
        detail={"surface": surface, "requeue_accepted": accepted},
    )


def refresh_credential(context: ActionContext) -> ActionResult:
    """Renew the credential. Notably *not* followed by a retry from here.

    Re-queueing on the back of a refresh would report a fix on the strength of
    two return values and no observation. The sweep re-runs the probe instead.
    """
    evidence = _target(context)
    channel = str(evidence.detail.get("channel", evidence.surface))
    renewed = context.capabilities.refresh_credential(channel)
    return ActionResult(
        action=REFRESH_CREDENTIAL,
        performed=True,
        detail={"channel": channel, "renewed": renewed},
    )


def reclaim_space(context: ActionContext) -> ActionResult:
    """Free what is safely freeable on the exhausted surface."""
    surface = _target(context).surface
    freed = context.capabilities.reclaim_space(surface)
    return ActionResult(
        action=RECLAIM_SPACE,
        performed=True,
        detail={"surface": surface, "bytes_reclaimed": freed},
    )


#: Floors chosen against the ceilings in :mod:`deadman.diagnose.grounding`.
#: Every one sits above ``Method.REPORTED``'s 0.4, so a hypothesis leaning on a
#: third party's "it published fine" can never move infrastructure however
#: confidently the model phrased it. Renewing a credential and deleting files
#: are held higher than a retry because a retry is the cheapest to be wrong
#: about.
_SHIPPED: tuple[Action, ...] = (
    Action(
        name=RETRY_NOW,
        cause=Cause.TRANSIENT_UPSTREAM,
        intent="re-queue the work immediately; the far end was briefly unavailable",
        requires="requeue",
        min_confidence=0.5,
        run=retry_now,
    ),
    Action(
        name=REFRESH_CREDENTIAL,
        cause=Cause.EXPIRED_CREDENTIAL,
        intent="renew the channel credential; do not re-queue until a probe re-reads the surface",
        requires="refresh_credential",
        min_confidence=0.6,
        run=refresh_credential,
    ),
    Action(
        name=RECLAIM_SPACE,
        cause=Cause.RESOURCE_EXHAUSTION,
        intent="free what is safely freeable on the exhausted surface",
        requires="reclaim_space",
        min_confidence=0.6,
        run=reclaim_space,
    ),
)


def default_registry() -> Registry:
    """A fresh registry holding the shipped actions.

    Fresh rather than a module-level singleton so a caller cannot mutate the
    table another caller is selecting from, and so a deployment that wants a
    narrower set can build its own without unregistering anything.
    """
    registry = Registry()
    for action in _SHIPPED:
        registry.register(action)
    return registry
