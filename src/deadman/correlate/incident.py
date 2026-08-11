"""What a correlation is, as a type.

The one field this module exists for is :attr:`Incident.basis`. Everything
else here is bookkeeping; ``basis`` is the honest label on the claim.

**Inferred is not traversed.** A lineage-graph monitor answers "what else does
this affect?" by walking edges somebody declared. Nothing declares an edge
between free bytes on a laptop volume and a post at a third-party scheduler,
and nobody is going to write one. So the relationship in an ``Incident`` was
*reasoned to* from co-occurrence plus cited evidence — which means it can be
wrong in ways a traversal cannot, and a reader is entitled to know which kind
of claim they are being handed before they act on it. It is a field, and it is
rendered, rather than a tone the prose happens to take.

**An uncorrelated candidate is a state, not a null.** Faults that co-occurred
and could not be tied together are a real finding: it says these surfaces went
down together and we could not establish why. Returning nothing would erase
that, so the incident is returned with the relationship unestablished, the
reason in plain words, and every surface listed as unexplained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from deadman.diagnose.schema import Diagnosis


class Basis(str, Enum):
    """How the relationship between these surfaces was arrived at."""

    INFERRED = "inferred"
    """Reasoned to from co-occurrence and cited evidence. The only kind this
    system can produce, because no lineage graph spans these surfaces."""

    TRAVERSED = "traversed"
    """Read off a declared dependency edge. Nothing in this repo can produce
    one. It exists so a stored incident can still say which kind it was if a
    real graph ever arrives for some subset of surfaces — an inferred claim
    and a traversed one carry different weight and must not silently merge.
    ``test_nothing_here_can_produce_a_traversed_basis`` pins that.
    """


class CorrelationStatus(str, Enum):
    """Three states, for the same reason :class:`Observation` has three."""

    CORRELATED = "correlated"
    """A shared cause was inferred across two or more faulting surfaces, and
    every fact under it was quoted out of the evidence supplied."""

    UNCORRELATED = "uncorrelated"
    """We got an answer and it did not establish a cross-surface relationship —
    it tied only one surface, or it was rejected for asserting something it was
    not given. NOT a finding that the faults are independent."""

    UNAVAILABLE = "unavailable"
    """No usable answer at all. We learned nothing about whether these faults
    are related, which is different from learning that they are not."""


@dataclass(frozen=True)
class Incident:
    """Co-occurring faults, and what could be established about why."""

    status: CorrelationStatus
    basis: Basis

    surfaces: tuple[str, ...]
    """The faulting surfaces the shared cause actually ties together — read off
    the citations, not off the window. A surface that merely happened to be
    broken at the same time is not a member of the incident."""

    candidate_surfaces: tuple[str, ...]
    """Everything the window swept in, member or not. Kept so a reader can see
    what was considered and rejected, not only what survived."""

    shared_cause: str
    """The hypothesised cause, in the model's prose. A hypothesis, always: it
    is never rendered or consumed as fact. Empty when nothing was said."""

    confidence: float
    """What the system will stand behind, in ``[0, 1]``. The diagnosis's own
    capped number — capped by the trust tier of the weakest cited evidence —
    carried through unchanged. Always ``0.0`` unless ``CORRELATED``."""

    claimed_confidence: float
    """What the model asked for, before capping. The gap is a signal."""

    unexplained: tuple[str, ...]
    """Surfaces in the window the correlation did not account for: the other
    faults, and every blind spot beside them.

    Listed rather than folded into a discount on :attr:`confidence`. Turning
    "we could not see the relay" into a slightly smaller number would tell a
    reader we were less sure and never tell them of what.
    """

    reason: str
    """Why it went the way it did, in plain words. An incident that cannot say
    what stopped it is an alert a human cannot act on."""

    evidence_ids: tuple[str, ...]
    diagnosis: Diagnosis
    """The full provenance: model, temperature, prompt version, citations, and
    the rejected claims when there were any."""

    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if self.status is not CorrelationStatus.CORRELATED and self.confidence != 0.0:
            raise ValueError(
                f"a {self.status.value} incident cannot carry confidence "
                f"{self.confidence}; no relationship was established to be confident in"
            )
        if self.status is CorrelationStatus.CORRELATED and len(self.surfaces) < 2:
            raise ValueError(
                f"a correlated incident spans at least two surfaces, got {self.surfaces}; "
                f"one surface is not a relationship"
            )
