"""The rule: infer freely, invent never.

A language model handed a disk trend and an HTTP 500 body will happily
produce "the OAuth token expired". It is a plausible sentence and it may even
be true, but nothing in front of it said so, and a monitor that reports
plausible sentences as findings is a worse instrument than no monitor at all —
it manufactures confident wrong answers at machine speed.

So the split is drawn between two things a response contains:

* the **hypothesis**, which is inference, is allowed to be new text, and is
  the reason a model is in this pipeline at all;
* the **facts** it rests on, which must each be quoted verbatim out of one
  named piece of supplied evidence.

Grounding is checked per-evidence, not across the whole bundle. Attributing
the scheduler's 500 to the disk read is a causal claim; letting it through as
a citation because the string appears *somewhere* in the pile would smuggle
the interesting part of the reasoning past the check.

**Confidence is capped, not accepted.** The model's own number is a claim like
any other. A hypothesis resting on ``Method.REPORTED`` evidence — the
scheduler said so — cannot be held with high confidence no matter how sure the
model sounds, because that tier is a heartbeat wearing a hat. The weakest
cited evidence sets the ceiling: a strong read does not launder a weak one it
is reasoning alongside.

Where the enforcement ends
--------------------------

Worth stating plainly, because a check described as airtight is more dangerous
than one whose edges are known.

What is mechanically enforced: every cited fact is verbatim in the evidence it
is attributed to, every evidence id referenced — in the citations array *or*
loose in the prose — was actually supplied, and the confidence attached is one
the cited tiers can carry. Any failure discards the whole response.

What is not, and cannot be: arbitrary unsupported prose inside the hypothesis
itself. No deterministic check can tell an inference from an assertion in free
text. The design answer is structural rather than detective — facts and
inference live in different fields, only the facts field is believed, and the
hypothesis is never rendered or consumed as fact. It is labelled a hypothesis,
it carries a capped confidence, and the layer that acts on it (DM1.6) executes
deterministic code selected by the diagnosis rather than anything the model
wrote. A fabricated sentence in a hypothesis is therefore visible to a human
and inert to the machine, which is the most this boundary can honestly claim.
"""

from __future__ import annotations

import re

from deadman.diagnose.schema import Citation
from deadman.evidence.model import Evidence, Method

#: A one-character quote matches nearly any corpus, so accepting one would let
#: a model satisfy the citation requirement without citing anything.
MIN_QUOTE_CHARS = 2

#: How much confidence each evidence tier can support. These mirror
#: ``Method``'s trust ordering: a read of the destination's own API can carry
#: a near-certain hypothesis; a third party's assertion that it went fine
#: cannot carry much of anything.
_CEILING_BY_METHOD: dict[Method, float] = {
    Method.DESTINATION_API: 1.0,
    Method.DESTINATION_PUBLIC: 0.9,
    Method.ACTIVE_CANARY: 0.85,
    Method.LOCAL_ARTIFACT: 0.8,
    Method.REPORTED: 0.4,
}

#: Reasoning that leans on a surface we could not see is reasoning around a
#: hole. It can still be worth reporting, but never as a confident finding.
BLIND_CEILING = 0.5

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Case and whitespace are formatting, not content.

    Deliberately conservative: it does not strip punctuation or stem words,
    because "500" and "5000" must stay different and "not published" must not
    quietly match "published".
    """
    return _WHITESPACE.sub(" ", text).strip().lower()


def corpus_for(evidence: Evidence) -> str:
    """Everything this one observation actually says, as quotable text.

    ``Evidence.detail`` is unstructured on purpose — it is the raw failure
    material, and reading messy heterogeneous evidence is the model's job. It
    follows that the detail has to be quotable, keys as well as values: a
    model pointing at ``slope_gb_per_day`` is pointing at something real.
    """
    parts = [
        evidence.surface,
        evidence.observation.value,
        evidence.method.value,
        evidence.summary,
        evidence.source,
        evidence.read_at.isoformat(),
    ]
    for key, value in evidence.detail.items():
        parts.append(f"{key}={value}")
        parts.append(str(key))
        parts.append(str(value))
    return normalize(" | ".join(parts))


def reject_reason(claim: Citation, by_id: dict[str, Evidence]) -> str | None:
    """Why this citation cannot stand, or ``None`` if it can.

    Fails closed in every direction: an id that was never supplied, a quote
    too short to mean anything, and a quote that simply is not there all come
    back as rejections rather than warnings.
    """
    evidence = by_id.get(claim.evidence_id)
    if evidence is None:
        return (
            f"unknown evidence id {claim.evidence_id!r}: no such evidence was "
            f"supplied, so this claim rests on nothing"
        )

    quote = normalize(claim.quote)
    if len(quote) < MIN_QUOTE_CHARS:
        return (
            f"quote {claim.quote!r} is shorter than {MIN_QUOTE_CHARS} characters; "
            f"a fragment that short matches almost anything and cites nothing"
        )

    if quote not in corpus_for(evidence):
        return (
            f"quote {claim.quote!r} is not present in evidence "
            f"{claim.evidence_id}: the model asserted a fact it was not given"
        )
    return None


def confidence_ceiling(evidence: list[Evidence]) -> float:
    """The most confidence the cited evidence can support.

    No evidence means no confidence — a hypothesis with nothing under it is a
    guess, and guesses do not get a number.
    """
    if not evidence:
        return 0.0

    ceiling = min(_CEILING_BY_METHOD.get(e.method, 0.0) for e in evidence)
    if any(e.is_blind for e in evidence):
        ceiling = min(ceiling, BLIND_CEILING)
    return ceiling
