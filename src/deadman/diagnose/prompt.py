"""What the model is shown, and the contract it must answer in.

Two things about this file are load-bearing beyond the wording.

**The prompt is versioned and the version is real.** Every ``Diagnosis``
records ``PROMPT_VERSION``, which is worthless if the constant can drift away
from the text. :func:`prompt_fingerprint` is pinned by a test, so editing the
instructions without bumping the version fails the suite. A hypothesis from
last week can then still be explained by the prompt that produced it.

**The prompt asks for citations, it does not rely on them.** Instructions are
a request; :mod:`deadman.diagnose.grounding` is the enforcement. Everything
here exists to make the model's job easy, not to make the check unnecessary —
a model that ignores all of it produces a rejected diagnosis, not a bad one
that slips through.

The instructions also spend a paragraph on ``UNOBSERVABLE`` on purpose. A
model shown a surface with no result will reason as though it is fine, which
is the exact substitution — blindness read as health — that this codebase
exists to prevent.
"""

from __future__ import annotations

import hashlib

from deadman.diagnose.schema import evidence_id
from deadman.evidence.model import Evidence

PROMPT_VERSION = "diagnose/v1"

RESPONSE_CONTRACT = """{
  "hypothesis": "<one causal explanation, in plain prose>",
  "confidence": <number between 0 and 1>,
  "citations": [
    {"evidence_id": "<an id from the evidence above>", "quote": "<text copied verbatim>"}
  ]
}"""

INSTRUCTIONS = f"""\
You are diagnosing infrastructure that fails silently. Deterministic probes
have already established WHAT each surface is doing. Your job is the part they
cannot do: say WHY, as a single causal hypothesis that accounts for the
evidence below.

Three rules, in order of importance.

1. You may infer. You may not invent. The hypothesis is yours to reason out
   and may be new text. Every FACT you lean on must be copied verbatim from
   one piece of the evidence below and cited against that piece's id. A quote
   that does not appear character-for-character in the evidence you attribute
   it to will be rejected, and one rejected quote discards your entire answer.
   If the evidence cannot support a conclusion, say so in the hypothesis and
   cite what little there is. That is a useful answer. A confident invented
   one is not.

2. An UNOBSERVABLE surface is blind, not healthy. It means the probe could not
   see, and it says nothing whatsoever about whether that surface is working.
   Do not reason as though it passed and do not reason as though it failed.
   If your hypothesis depends on knowing, say that it depends on knowing.

3. Do not refer to any evidence id other than the ones listed below. Do not
   propose a remediation, and do not claim anything has been fixed; other
   parts of this system decide that and prove it.

Your confidence will be capped by the trust tier of the evidence you cite, so
citing the strongest available evidence for a claim is in your interest.

Answer with JSON matching this shape and nothing else:

{RESPONSE_CONTRACT}
"""


def render_evidence(evidence: Evidence) -> str:
    """One observation, id first, raw detail included.

    ``detail`` goes in whole and unsummarised. It is heterogeneous by design —
    a byte count here, a worker log line there — and pre-digesting it into
    something tidy would throw away exactly the material this layer is for.
    """
    lines = [
        f"id: {evidence_id(evidence)}",
        f"surface: {evidence.surface}",
        f"observation: {evidence.observation.value}",
        f"how we learned it: {evidence.method.value}",
        f"read at: {evidence.read_at.isoformat()}",
        f"source: {evidence.source}",
        f"summary: {evidence.summary}",
        "detail:",
    ]
    lines.extend(f"  {key}: {value}" for key, value in evidence.detail.items())
    return "\n".join(lines)


def render_prompt(evidence: list[Evidence]) -> str:
    body = "\n\n".join(render_evidence(e) for e in evidence)
    return f"{INSTRUCTIONS}\n\nEVIDENCE\n========\n\n{body}\n"


def prompt_fingerprint() -> str:
    """Digest of the instruction text and the response contract.

    Pinned by a test so ``PROMPT_VERSION`` cannot silently stop describing the
    prompt it names.
    """
    return hashlib.sha256(INSTRUCTIONS.encode()).hexdigest()[:16]
