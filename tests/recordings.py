"""Replay recorded model responses so the diagnosis tests never call a model.

See ``tests/recorded/README.md`` for what a recording is and the honest note
about how these particular ones were produced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from deadman.evidence.model import Evidence, Method, Observation

RECORDED = Path(__file__).parent / "recorded"


def load_bundle(name: str) -> list[Evidence]:
    raw = json.loads((RECORDED / f"{name}.json").read_text())
    return [
        Evidence(
            surface=row["surface"],
            observation=Observation(row["observation"]),
            method=Method(row["method"]),
            summary=row["summary"],
            source=row["source"],
            read_at=datetime.fromisoformat(row["read_at"]),
            detail=row["detail"],
        )
        for row in raw["evidence"]
    ]


@dataclass
class RecordedClient:
    """A :class:`~deadman.diagnose.engine.ModelClient` that replays a file.

    Records the prompts it was handed, so a test can assert what the model was
    actually shown — and assert it was not called at all when it should not
    have been.
    """

    name: str

    def __post_init__(self) -> None:
        self._recording = json.loads((RECORDED / f"{self.name}.json").read_text())
        self.prompts: list[str] = []

    @property
    def bundle(self) -> list[Evidence]:
        return load_bundle(self._recording["bundle"])

    @property
    def model(self) -> str:
        return self._recording["model"]

    @property
    def temperature(self) -> float:
        return self._recording["temperature"]

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._recording["response"]


@dataclass
class RaisingClient:
    """A model that is simply down."""

    model: str = "gemini-3.5-flash"
    temperature: float = 0.0

    def complete(self, prompt: str) -> str:
        raise ConnectionError("vertex ai endpoint refused the connection")
