"""What a diagnosis is, as a type.

The evidence model (:mod:`deadman.evidence.model`) has two load-bearing ideas:
absence is a state rather than a null, and how you learned something is part
of what you learned. Both carry straight into this layer.

**A rejected diagnosis is a state, not a null.** When the model asserts
something the evidence does not support, the engine does not return ``None``
and it does not raise. It returns a ``Diagnosis`` with status ``UNGROUNDED``,
zero confidence, and the specific claims that failed. A caller cannot mistake
that for "no problem", and a human reading the report can see exactly what the
model tried to say and why it was not allowed to.

**How the diagnosis was produced is part of the diagnosis.** Model,
temperature and prompt version ride on every one of these, including the
rejected ones. A hypothesis is not reproducible without them, and an
irreproducible hypothesis is not evidence of anything.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from deadman.evidence.model import Evidence


class DiagnosisStatus(str, Enum):
    """Three states, for the same reason :class:`Observation` has three."""

    GROUNDED = "grounded"
    """Every fact the hypothesis rests on was quoted verbatim out of the
    supplied evidence. The hypothesis itself is still a hypothesis."""

    UNGROUNDED = "ungrounded"
    """The model asserted at least one thing the evidence does not support, so
    the whole answer was rejected. Not a verdict about the estate — a verdict
    about this particular model response."""

    UNAVAILABLE = "unavailable"
    """The model could not be consulted, or answered unusably. The diagnosis
    layer is blind, exactly as ``Observation.UNOBSERVABLE`` means a probe is.
    Never to be read as "nothing is wrong"."""


@dataclass(frozen=True)
class Citation:
    """One fact, and the evidence it was lifted from.

    ``quote`` must appear verbatim (modulo case and whitespace) in that
    evidence's text. This is the entire enforcement mechanism: a model that
    wants to assert something must find it in the material it was given.
    """

    evidence_id: str
    quote: str


@dataclass(frozen=True)
class Diagnosis:
    """A causal hypothesis, the facts under it, and how it was produced."""

    status: DiagnosisStatus

    hypothesis: str
    """The inference. Free text on purpose — this is the part the model is
    genuinely for. Retained even when ``UNGROUNDED`` so a human can read what
    was rejected rather than being told only that something was."""

    confidence: float
    """What the system is willing to stand behind, in ``[0, 1]``. Not the
    model's own number: capped by the trust tier of the evidence cited (see
    :func:`deadman.diagnose.grounding.confidence_ceiling`). Always ``0.0``
    unless ``GROUNDED``."""

    claimed_confidence: float
    """What the model said, before capping. Kept because the gap between the
    two is itself a signal worth reading."""

    evidence_ids: tuple[str, ...]
    """The evidence this rests on. Empty when nothing survived grounding."""

    citations: tuple[Citation, ...]
    model: str
    temperature: float
    prompt_version: str

    rejected_claims: tuple[str, ...] = ()
    """Why the answer was thrown out, one reason per failed claim."""

    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if self.status is not DiagnosisStatus.GROUNDED and self.confidence != 0.0:
            raise ValueError(
                f"a {self.status.value} diagnosis cannot carry confidence "
                f"{self.confidence}; it rests on nothing the system verified"
            )

    @property
    def is_actionable(self) -> bool:
        """Whether a remediation may be selected from this.

        DM1.6 keys on this. An ungrounded hypothesis reaching an executor is
        the model taking an action on a fact it made up, which is the single
        worst outcome available to this design.
        """
        return self.status is DiagnosisStatus.GROUNDED


def evidence_id(evidence: Evidence) -> str:
    """A stable, human-readable handle for one observation.

    ``Evidence`` has no id of its own — it is a frozen record of a moment, and
    adding a field to it would ripple through every probe. The id is derived
    instead, from the things that make an observation that observation: which
    surface, when it was read, and what it said.

    Two reads of one surface must not collide, or a model could cite this
    morning's healthy read to support a claim about tonight's fault.
    """
    material = f"{evidence.surface}|{evidence.read_at.isoformat()}|{evidence.summary}"
    digest = hashlib.sha256(material.encode()).hexdigest()[:8]
    return f"{evidence.surface}#{digest}"
