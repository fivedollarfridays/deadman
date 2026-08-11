"""The two stand-ins the demo needs, kept apart from the sequence itself.

Both are honest about what they are. Neither is used by the package, the test
suite, or the deployed service; they exist only so the demo can be run by
someone who does not have Kevin's phone or a Vertex project.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from deadman.probes.sms_relay import DispatchOutcome, DispatchResult


@dataclass
class StubRelay:
    """Stands in for the phone. Broken until the queue is drained."""

    broken: bool = True
    sent: set[str] = field(default_factory=set)
    attempts: int = 0

    def send_canary(self, token: str) -> DispatchResult:
        self.attempts += 1
        if self.broken:
            return DispatchResult(
                outcome=DispatchOutcome.REJECTED,
                why="relay host returned 503 Service Unavailable",
                detail={"http_status": 503, "endpoint": "termux-sms-send"},
            )
        self.sent.add(token)
        return DispatchResult(outcome=DispatchOutcome.ACCEPTED, detail={"http_status": 200})

    def find(self, token: str) -> bool:
        """Sent-folder reader: the only place a canary is confirmed."""
        return token in self.sent


@dataclass
class ScriptedClient:
    """A stand-in model for rehearsal, so the demo runs with no network.

    **This is not a model and does not pretend to be one.** It reads the
    evidence ids and summaries back out of the prompt and returns a
    correctly-shaped response citing them. It exists because the committed
    recordings cite fixed ids, while this demo generates fresh evidence with a
    new canary token every run, so no static recording can ever resolve
    against it.

    The submitted demo runs with ``--live``. This path is for rehearsing the
    sequence and for proving the *pipeline* end to end without spending a call.
    """

    model: str = "scripted-demo-stub"
    temperature: float = 0.0

    def complete(self, prompt: str) -> str:
        ids = re.findall(r"^id: (.+)$", prompt, re.MULTILINE)
        summaries = re.findall(r"^summary: (.+)$", prompt, re.MULTILINE)
        citations = [{"evidence_id": i, "quote": s} for i, s in zip(ids, summaries, strict=False)]
        return json.dumps(
            {
                "hypothesis": (
                    "The relay host is refusing sends with a 503, which is an upstream "
                    "outage rather than anything wrong with the credential or the "
                    "message. The evidence does not say how long it will last."
                ),
                "confidence": 0.8,
                "citations": citations,
            }
        )
