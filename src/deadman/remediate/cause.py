"""What the cited evidence says went wrong.

A fault class is not a cause. "The post did not reach the destination" is one
fault with at least four causes behind it, and the correct response to three of
them is not the correct response to the fourth:

* expired token — re-queueing fails identically, so it is wasted motion;
* policy refusal — re-queueing is *worse* than nothing, it burns rate limit
  against a decision the platform already made;
* disconnected channel — re-queueing sends to nowhere;
* transient 5xx — re-queueing is exactly right, and delaying it costs the post.

So this module answers the question selection actually needs answered, and it
answers it from the evidence rather than from the fault.

What reads what
---------------

The division of labour with the diagnosis layer is the load-bearing part.

The model decides **which evidence rows are causal** — that is inference over
heterogeneous, unstructured failure material, and it is the reason a model is
in this pipeline. It has no say in what those rows mean.

This module decides **what those rows say**, and everything it reads was
written by probe code: status codes, error codes, and probe-authored summaries.
No model text reaches a classifier here, and the output is a value from a
closed enum, so there is no path from a generated string to a selected action.

Two rules that matter more than the token lists
-----------------------------------------------

**Only faults contribute a cause.** A ``HEALTHY`` row has nothing to remediate,
and an ``UNOBSERVABLE`` row is a statement about our blindness — acting on it
would be acting on an absence of evidence, which is the failure this project
exists to catch.

**Unrecognised is UNKNOWN, and UNKNOWN escalates.** The tempting default is to
treat anything unfamiliar as probably-transient and retry it. That default is
wrong in exactly the cases that matter, so it is not the default here.
"""

from __future__ import annotations

from enum import Enum

from deadman.evidence.model import Evidence, Observation


class Cause(str, Enum):
    """The closed set of things this system knows how to recognise."""

    POLICY_REJECTION = "policy_rejection"
    """The platform looked at the artifact and refused it. No code in this
    repo can fix a caption."""

    CHANNEL_DISCONNECTED = "channel_disconnected"
    """The destination is no longer wired up. Sending again sends nowhere."""

    EXPIRED_CREDENTIAL = "expired_credential"
    """Authentication failed. Everything downstream of it will keep failing
    the same way until it is renewed."""

    RESOURCE_EXHAUSTION = "resource_exhaustion"
    """Something ran out — space, quota, inodes. Usually the real cause of a
    fault that presents somewhere else entirely."""

    TRANSIENT_UPSTREAM = "transient_upstream"
    """The other end was briefly unable to serve the request. The only cause
    here that an immediate retry actually answers."""

    UNKNOWN = "unknown"
    """No rule matched. Not a diagnosis of anything — a statement that this
    module did not recognise the failure."""


#: Most blocking first. Ordered by how harmful it is to act on a lower cause
#: while a higher one holds: a retry issued under a dead credential is wasted,
#: a retry issued under a policy refusal is actively harmful, and nothing is
#: made worse by renewing a credential while a disk is also filling.
#:
#: Total by construction — a cause missing from this tuple would sort
#: arbitrarily against the rest, which is how a retry gets ahead of a
#: credential failure. ``test_precedence_is_total_and_ends_in_unknown`` pins it.
PRECEDENCE: tuple[Cause, ...] = (
    Cause.POLICY_REJECTION,
    Cause.CHANNEL_DISCONNECTED,
    Cause.EXPIRED_CREDENTIAL,
    Cause.RESOURCE_EXHAUSTION,
    Cause.TRANSIENT_UPSTREAM,
    Cause.UNKNOWN,
)

#: Where probes put an HTTP status. Heterogeneous on purpose — the surfaces
#: share no schema, which is the premise of the whole project.
_STATUS_KEYS = ("http_status", "status_code", "status")

#: Where probes put something a human wrote about the failure.
_TEXT_KEYS = ("error_code", "error", "reason", "code", "body", "message", "detail")

#: Structured signals that a volume is the problem, independent of any text.
_RESOURCE_KEYS = ("runway_days", "slope_gb_per_day", "free_gb")

_TOKENS: tuple[tuple[Cause, tuple[str, ...]], ...] = (
    (Cause.POLICY_REJECTION, ("policy", "content_violation", "disallowed", "violation")),
    (Cause.CHANNEL_DISCONNECTED, ("disconnected", "not_connected", "channel_removed", "revoked")),
    (
        Cause.EXPIRED_CREDENTIAL,
        (
            "token_expired",
            "token expired",
            "expired_token",
            "invalid_grant",
            "unauthorized",
            "credential",
        ),
    ),
    (
        Cause.RESOURCE_EXHAUSTION,
        ("no space left", "enospc", "disk full", "quota exceeded", "out of space"),
    ),
)


def _status(evidence: Evidence) -> int | None:
    for key in _STATUS_KEYS:
        value = evidence.detail.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _text(evidence: Evidence) -> str:
    parts = [evidence.summary]
    parts.extend(str(evidence.detail[k]) for k in _TEXT_KEYS if k in evidence.detail)
    return " ".join(parts).lower()


def _from_status(status: int | None) -> set[Cause]:
    """Causes a status code alone establishes.

    Deliberately narrow. ``403`` is left out because it covers both a policy
    refusal and a dead credential and guessing between them picks the wrong
    action half the time; the text rules resolve it or nothing does. ``404``
    is left out because on these surfaces it *is* the fault — the post is
    absent — not the reason for it. ``429`` is left out because reading it as
    a transient 5xx selects an immediate retry, the one response guaranteed to
    make a rate limit worse; it escalates until a backoff action exists.
    """
    if status is None:
        return set()
    if 500 <= status <= 599:
        return {Cause.TRANSIENT_UPSTREAM}
    if status == 401:
        return {Cause.EXPIRED_CREDENTIAL}
    return set()


def causes_in(evidence: Evidence) -> set[Cause]:
    """Every cause this one observation supports. Empty unless it is a fault."""
    if evidence.observation is not Observation.FAULT:
        return set()

    found = _from_status(_status(evidence))

    text = _text(evidence)
    found.update(cause for cause, tokens in _TOKENS if any(t in text for t in tokens))

    if any(key in evidence.detail for key in _RESOURCE_KEYS):
        found.add(Cause.RESOURCE_EXHAUSTION)
    return found


def classify(evidence: list[Evidence]) -> Cause:
    """The one cause to act on, across everything the diagnosis cited.

    Several can be true at once — a channel can be rate limited *and* out of
    credential — so the most blocking wins rather than the first found.
    Order of the input never changes the answer.
    """
    found: set[Cause] = set()
    for one in evidence:
        found.update(causes_in(one))

    return next((cause for cause in PRECEDENCE if cause in found), Cause.UNKNOWN)
