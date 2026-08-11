"""Gemini, reached through the Agent Development Kit.

The one place in this package that talks to a model. Everything else —
prompting, grounding, the confidence ceiling, the whole judgement about
whether an answer may be believed — is model-agnostic and fully exercised
offline, because it has to keep working when this file is swapped out.

**The SDK is imported inside the constructor, never at module scope.** The
package itself declares no dependencies (see ``pyproject.toml``) and the test
suite must never be able to reach Vertex, so a stray top-level
``import google.adk`` would make the offline guarantee depend on nobody having
installed one. Reaching for it late also lets the adapter be imported
anywhere without a guard.

**Construction fails loudly, ``complete`` does not.** A missing SDK or bad
configuration is a startup problem and is raised at startup — a monitor that
finds out its brain is absent while diagnosing an outage has become part of
the outage. Once running, a failed call is left to raise and is caught by
:class:`deadman.diagnose.engine.DiagnosisEngine`, which turns it into an
``UNAVAILABLE`` diagnosis rather than a crash or, worse, a verdict.

.. warning::

   The ADK call shape below is **not exercised by the test suite**. This
   environment has no GCP credentials and no ``google-adk`` install (the same
   constraint that blocked DM1.8's live deploy), so it is written to the
   documented ADK interface and needs one live smoke test before the demo:

   .. code-block:: python

      from deadman.diagnose.engine import DiagnosisEngine
      from deadman.diagnose.gemini import GeminiClient

      print(DiagnosisEngine(client=GeminiClient()).diagnose(evidence))

   When that runs, save the raw response into ``tests/recorded/`` as a real
   capture and retire the authored ones. Nothing else needs to change: the
   engine only ever sees a string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: The contest requires Gemini; this is the model the sprint brief names.
#: Overridable per instance, and recorded on every diagnosis either way.
DEFAULT_MODEL = "gemini-3.5-flash"

#: Diagnosis is not a creative task, and a hypothesis that cannot be
#: re-derived from its own provenance record is not much of a record.
DEFAULT_TEMPERATURE = 0.0

AGENT_NAME = "deadman_diagnostician"
APP_NAME = "deadman"


class ModelSdkMissing(RuntimeError):
    """Raised at construction when the ADK is not installed."""


_INSTALL_HINT = (
    "google-adk is not installed, so the diagnosis layer has no model to "
    "reach. Install it with: pip install 'deadman[gemini]'"
)


@dataclass
class GeminiClient:
    """A :class:`~deadman.diagnose.engine.ModelClient` backed by Gemini/ADK."""

    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    app_name: str = APP_NAME
    user_id: str = APP_NAME
    _runner: Any = field(default=None, init=False, repr=False)
    _types: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            from google.adk.agents import LlmAgent
            from google.adk.runners import InMemoryRunner
            from google.genai import types
        except ImportError as exc:
            raise ModelSdkMissing(_INSTALL_HINT) from exc

        agent = LlmAgent(
            name=AGENT_NAME,
            model=self.model,
            # The whole instruction lives in the rendered prompt so that one
            # versioned, fingerprinted string is the complete record of what
            # the model was told. Splitting it across a system instruction
            # would make `prompt_version` a partial account.
            instruction="",
            generate_content_config=types.GenerateContentConfig(
                temperature=self.temperature,
                response_mime_type="application/json",
            ),
        )
        self._runner = InMemoryRunner(agent=agent, app_name=self.app_name)
        self._types = types

    def complete(self, prompt: str) -> str:
        """One turn. Raises on failure; the engine converts that to blindness.

        A fresh session per call on purpose: each diagnosis must rest on the
        evidence it was handed and nothing else, and a carried-over session
        would let last sweep's facts leak into this sweep's citations.
        """
        session = self._runner.session_service.create_session_sync(
            app_name=self.app_name, user_id=self.user_id
        )
        message = self._types.Content(
            role="user", parts=[self._types.Part(text=prompt)]
        )

        chunks: list[str] = []
        for event in self._runner.run(
            user_id=self.user_id, session_id=session.id, new_message=message
        ):
            if not event.is_final_response() or not event.content:
                continue
            chunks.extend(part.text for part in (event.content.parts or []) if part.text)
        return "".join(chunks)
