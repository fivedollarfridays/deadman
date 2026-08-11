"""The registry: a closed table from cause to code.

Two properties this exists to hold.

**Selection is a lookup, not a generation.** The key is a
:class:`~deadman.remediate.cause.Cause`, a closed enum. There is no string from
a model anywhere on the path between a diagnosis and an executed function, so
the worst a compromised or hallucinating model can do is push the selection
toward the wrong *registered* action — never toward an action nobody wrote.

**Action bodies are code on disk.** :meth:`Registry.register` refuses any
callable it cannot find a source file for, which is what a body built by
``exec``/``compile`` at runtime looks like. Worth being honest about the reach
of that check: it stops the obvious route and it is not a sandbox. A
sufficiently determined caller writing a file and importing it defeats it. What
it does guarantee is that every action in this system is reviewable code that
existed before the run, which is the property the design actually needs.

A capability an action needs but has not been given is an action that cannot
run. The executor escalates rather than reporting a plan it cannot carry out —
reporting one would be the heartbeat problem again, one layer up.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from deadman.diagnose.schema import Diagnosis
from deadman.evidence.model import Evidence
from deadman.remediate.cause import Cause


class NonDeterministicAction(Exception):
    """Raised when an action body did not come from reviewable source."""


@dataclass(frozen=True)
class Capabilities:
    """What this deployment is actually able to do.

    Every one is optional and every one defaults to absent, because a deadman
    that cannot reach the remediation endpoint must say so rather than plan
    around it. Injected rather than imported so nothing in this package holds a
    live handle to anyone's infrastructure.
    """

    requeue: Callable[[str], bool] | None = None
    """Re-submit the pending work for a surface. Returns whether it was
    accepted — which is a claim about the queue, never about the outcome."""

    refresh_credential: Callable[[str], bool] | None = None
    """Renew the credential for a channel."""

    reclaim_space: Callable[[str], int] | None = None
    """Free what is safely freeable on a surface. Returns bytes reclaimed.

    Takes the surface rather than a path so this package holds no knowledge of
    anyone's host layout; mapping ``host:disk/`` to a directory is a fact about
    a deployment, not about remediation."""


_CAPABILITY_NAMES = frozenset(f.name for f in fields(Capabilities))


@dataclass(frozen=True)
class ActionContext:
    """Everything an action body is allowed to see."""

    diagnosis: Diagnosis
    evidence: tuple[Evidence, ...]
    """The cited evidence, resolved — not the whole sweep. An action reasons
    over what the diagnosis rested on."""

    cause: Cause
    capabilities: Capabilities


@dataclass(frozen=True)
class ActionResult:
    """What the executor did, and nothing about whether it worked.

    ``performed`` is a fact about this process: the code ran and did not raise.
    Whether the surface recovered is a fact about the surface, and only a fresh
    observation can establish it — that is DM1.7's job, and the reason there is
    deliberately no ``success`` field here for a caller to read as one.
    """

    action: str
    performed: bool
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Action:
    """One remediation: what it answers, what it needs, and the code that does it."""

    name: str
    cause: Cause
    """The single cause this answers. One action per cause, so selection is a
    function rather than a race between candidates."""

    intent: str
    """What it will do, in words, for the plan a human reads before approving
    a wet run."""

    requires: str
    """The :class:`Capabilities` field this cannot run without."""

    min_confidence: float
    """The floor the diagnosis must clear. Confidence arrives already capped by
    the trust tier of the cited evidence, so this is what keeps a hypothesis
    resting on a third party's self-report from moving real infrastructure."""

    run: Callable[[ActionContext], ActionResult]


def _reject_generated_body(action: Action) -> None:
    source = inspect.getsourcefile(action.run) if inspect.isroutine(action.run) else None
    if source is None or not Path(source).is_file():
        raise NonDeterministicAction(
            f"action {action.name!r} is not defined in a source file on disk; "
            f"action bodies are reviewable code, never built at runtime"
        )
    try:
        inspect.getsource(action.run)
    except OSError as exc:  # source file exists but does not contain the body
        raise NonDeterministicAction(
            f"action {action.name!r} is not defined in a source file that can be read back: {exc}"
        ) from exc


class Registry:
    """The table. Deliberately small and deliberately closed."""

    def __init__(self) -> None:
        self._by_cause: dict[Cause, Action] = {}

    def register(self, action: Action) -> None:
        _reject_generated_body(action)

        if action.requires not in _CAPABILITY_NAMES:
            raise ValueError(
                f"action {action.name!r} requires capability {action.requires!r}, "
                f"which is not one of {sorted(_CAPABILITY_NAMES)}"
            )
        if action.cause in self._by_cause:
            raise ValueError(
                f"cause {action.cause.value} is already answered by "
                f"{self._by_cause[action.cause].name!r}; selection must be a function"
            )
        self._by_cause[action.cause] = action

    def for_cause(self, cause: Cause) -> Action | None:
        """The action answering this cause, or ``None`` — which escalates.

        A cause with nothing behind it is not an oversight. Some failures have
        no safe automated response, and saying so is the correct answer.
        """
        return self._by_cause.get(cause)

    def actions(self) -> tuple[Action, ...]:
        return tuple(self._by_cause.values())
