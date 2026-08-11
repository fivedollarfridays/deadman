"""The diagnosis engine: ask the model, then refuse to take its word for it.

The shape here is deliberately the same as :func:`deadman.probes.base.run_probe`.
A probe that raises becomes a blind state rather than a fault, because a broken
instrument is not evidence about the estate. The same holds one layer up: a
model that is down, or that answers unreadably, leaves us unable to diagnose —
which is a fact about us, not about the infrastructure. It never becomes a
finding, and it never becomes an exception escaping into a sweep.

Three outcomes, and the distinction between the last two matters:

``GROUNDED``
    Every fact quoted checked out. The hypothesis stands, at a confidence the
    cited evidence can actually carry.

``UNGROUNDED``
    The model asserted something it was not given. We learned something real
    and bad about this response, and a human should see it.

``UNAVAILABLE``
    We could not get a readable answer at all. We learned nothing.

**Rejection is all-or-nothing.** A response with four good citations and one
invented fact is not three-quarters right; the hypothesis was reasoned from
the invented fact along with the rest, so keeping the survivors would leave a
conclusion standing on a premise that was thrown out. The whole answer goes,
and the hypothesis text is retained only so an operator can review what was
refused.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from deadman.diagnose.grounding import confidence_ceiling, reject_reason
from deadman.diagnose.prompt import PROMPT_VERSION, render_prompt
from deadman.diagnose.schema import Citation, Diagnosis, DiagnosisStatus, evidence_id
from deadman.evidence.model import Evidence

logger = logging.getLogger(__name__)

#: Ids look like ``surface#deadbeef``. Distinctive enough to spot in prose,
#: which is where a model smuggles a fabricated source when the citations
#: array is being checked.
_ID_IN_PROSE = re.compile(r"[A-Za-z0-9:/._-]+#[0-9a-f]{8}")


@runtime_checkable
class ModelClient(Protocol):
    """One turn of text in, one turn of text out.

    Kept this thin so the model is trivially swappable and trivially
    replayable. The real implementation is
    :class:`deadman.diagnose.gemini.GeminiClient`; the tests replay recordings
    through the same interface, which is why they need no network.
    """

    @property
    def model(self) -> str: ...

    @property
    def temperature(self) -> float: ...

    def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class DiagnosisEngine:
    """Turns evidence into a hypothesis the system is willing to stand behind."""

    client: ModelClient

    def diagnose(self, evidence: list[Evidence]) -> Diagnosis:
        if not evidence:
            # Nothing to reason over means anything said is invention. Do not
            # pay for the call and do not create the opportunity.
            return self._unavailable("no evidence supplied", hypothesis="")

        by_id = {evidence_id(e): e for e in evidence}

        try:
            raw = self.client.complete(render_prompt(evidence))
        except Exception as exc:  # noqa: BLE001 -- a silent model must not stop a sweep
            logger.warning("model %s raised: %r", self.client.model, exc)
            return self._unavailable(f"model raised {type(exc).__name__}: {exc}", hypothesis="")

        payload = _parse(raw)
        if payload is None:
            return self._unavailable("model response was not readable JSON", raw=raw[:500])

        return self._judge(payload, by_id)

    def _judge(self, payload: dict[str, Any], by_id: dict[str, Evidence]) -> Diagnosis:
        hypothesis = str(payload.get("hypothesis", "")).strip()
        claimed = payload.get("confidence")
        citations = _citations(payload)

        rejections = _rejections(hypothesis, claimed, citations, by_id)
        if rejections:
            return self._rejected(hypothesis, claimed, rejections)

        cited_ids = list(dict.fromkeys(c.evidence_id for c in citations))
        ceiling = confidence_ceiling([by_id[i] for i in cited_ids])
        return Diagnosis(
            status=DiagnosisStatus.GROUNDED,
            hypothesis=hypothesis,
            confidence=min(float(claimed), ceiling),
            claimed_confidence=float(claimed),
            evidence_ids=tuple(cited_ids),
            citations=tuple(citations),
            model=self.client.model,
            temperature=self.client.temperature,
            prompt_version=PROMPT_VERSION,
            detail={"confidence_ceiling": ceiling},
        )

    def _rejected(self, hypothesis: str, claimed: Any, reasons: list[str]) -> Diagnosis:
        logger.warning("rejected diagnosis from %s: %s", self.client.model, reasons)
        return Diagnosis(
            status=DiagnosisStatus.UNGROUNDED,
            hypothesis=hypothesis,
            confidence=0.0,
            claimed_confidence=_as_float(claimed),
            evidence_ids=(),
            citations=(),
            model=self.client.model,
            temperature=self.client.temperature,
            prompt_version=PROMPT_VERSION,
            rejected_claims=tuple(reasons),
        )

    def _unavailable(self, why: str, hypothesis: str = "", **detail: Any) -> Diagnosis:
        return Diagnosis(
            status=DiagnosisStatus.UNAVAILABLE,
            hypothesis=hypothesis,
            confidence=0.0,
            claimed_confidence=0.0,
            evidence_ids=(),
            citations=(),
            model=self.client.model,
            temperature=self.client.temperature,
            prompt_version=PROMPT_VERSION,
            rejected_claims=(why,),
            detail={"reason": why, **detail},
        )


def _rejections(
    hypothesis: str,
    claimed: Any,
    citations: list[Citation],
    by_id: dict[str, Evidence],
) -> list[str]:
    """Every way this answer fails, not just the first.

    All of them, because a human reviewing a rejection needs the whole picture
    of how the model went wrong, and because reporting one at a time turns
    prompt debugging into a guessing game.
    """
    reasons: list[str] = []

    if not citations:
        reasons.append(
            "no cited evidence: a hypothesis with nothing under it is a guess, "
            "however confidently it is phrased"
        )

    reasons.extend(r for c in citations if (r := reject_reason(c, by_id)))

    if not isinstance(claimed, (int, float)) or isinstance(claimed, bool):
        reasons.append(f"confidence {claimed!r} is not a number")
    elif not 0.0 <= float(claimed) <= 1.0:
        reasons.append(f"confidence {claimed} is outside the contracted range [0, 1]")

    reasons.extend(
        f"hypothesis refers to evidence id {found!r}, which was never supplied"
        for found in _ID_IN_PROSE.findall(hypothesis)
        if found not in by_id
    )
    return reasons


def _citations(payload: dict[str, Any]) -> list[Citation]:
    """Read the citations array defensively — a malformed entry becomes an
    unciteable claim rather than a crash, and gets rejected on its merits."""
    out: list[Citation] = []
    for row in payload.get("citations") or []:
        if not isinstance(row, dict):
            out.append(Citation(evidence_id=str(row), quote=""))
            continue
        out.append(
            Citation(
                evidence_id=str(row.get("evidence_id", "")),
                quote=str(row.get("quote", "")),
            )
        )
    return out


def _parse(raw: str) -> dict[str, Any] | None:
    """Pull the JSON object out of a model turn.

    Slices between the outermost braces rather than demanding a bare document,
    because models wrap answers in markdown fences and prefaces constantly and
    throwing away a good diagnosis over formatting would be its own kind of
    false negative.
    """
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
