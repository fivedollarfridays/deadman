"""The probe contract.

A probe answers one question about one surface and hands back
:class:`~deadman.evidence.model.Evidence`. It does not decide what to do, it
does not rank severity, and it does not talk to a model. Detection is
deterministic; everything inferential happens downstream.

**Probes never raise.** Not "rarely" and not "except for programmer error".
A probe that throws takes the whole sweep down with it, which means one
broken surface blinds you to every other surface, which is the outage this
project exists to catch. :func:`run_probe` is the only sanctioned way to
execute one, and it converts any escaping exception into an explicit blind
state.

**Never-raise is not the same as never-fail.** The bug this contract is
written against: a client that swallows every HTTP error and returns an
empty dict, so an expired token surfaces as "this dataset has no timestamp,
therefore it is stale, therefore here is an incident report." That is an
infrastructure failure laundered into a verdict about the estate. If a probe
cannot see, it must say it cannot see.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from deadman.evidence.model import Evidence, Observation, unobservable

logger = logging.getLogger(__name__)


@runtime_checkable
class Probe(Protocol):
    """One question, one surface, one piece of evidence."""

    @property
    def surface(self) -> str:
        """Stable id, e.g. ``metricool:fwtx_dao``. Correlation keys on this,
        so it must not drift between runs."""
        ...

    @property
    def question(self) -> str:
        """What this probe actually establishes, in plain words. Ends up in
        the report so a reader knows what was and was not checked."""
        ...

    def observe(self) -> Evidence:
        """Gather evidence. May raise; :func:`run_probe` contains it."""
        ...


def run_probe(probe: Probe) -> Evidence:
    """Execute a probe under the never-raise contract.

    Any escaping exception becomes ``UNOBSERVABLE`` naming the probe and the
    exception, never ``FAULT``. We did not learn the surface is broken. We
    learned our instrument is.
    """
    try:
        evidence = probe.observe()
    except Exception as exc:  # noqa: BLE001 — the entire point of this function
        logger.warning("probe %s raised: %r", probe.surface, exc)
        return unobservable(
            surface=probe.surface,
            source=f"probe:{type(probe).__name__}",
            why=f"probe raised {type(exc).__name__}: {exc}",
            question=probe.question,
        )

    if not isinstance(evidence, Evidence):  # defensive: a probe returning None
        logger.warning("probe %s returned %r, not Evidence", probe.surface, evidence)
        return unobservable(
            surface=probe.surface,
            source=f"probe:{type(probe).__name__}",
            why=f"probe returned {type(evidence).__name__}, not Evidence",
            question=probe.question,
        )

    if evidence.surface != probe.surface:  # correlation depends on stable ids
        logger.warning(
            "probe %s emitted evidence for %s", probe.surface, evidence.surface
        )
    return evidence


def sweep(probes: list[Probe]) -> list[Evidence]:
    """Run every probe. One surface failing never prevents the others running,
    because a partial picture that knows it is partial beats no picture."""
    return [run_probe(p) for p in probes]


def blind_spots(evidence: list[Evidence]) -> list[Evidence]:
    """The surfaces we could not see this sweep.

    Surfaced separately and deliberately. A run where four probes pass and one
    is blind is NOT a clean run, and a summary that reports "4 healthy" is the
    lie this project is about. Blind spots get their own line.
    """
    return [e for e in evidence if e.observation is Observation.UNOBSERVABLE]
