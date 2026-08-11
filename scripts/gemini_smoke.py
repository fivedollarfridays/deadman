#!/usr/bin/env python3
"""One live call to Gemini through the ADK.

Deliberately a script and not a test. The suite is hermetic and blocks
sockets, which is the right default and also means the one code path that
must reach Vertex can never be covered there. This is that path, run by hand.

See ``docs/gemini-verification.md`` for setup, and for the two failure modes
that point somewhere unhelpful (``gemini-3.5-flash`` is global-endpoint only,
and a fresh service account 403s for about a minute before it works).

    python scripts/gemini_smoke.py
"""

from __future__ import annotations

import os
import sys

from deadman.diagnose.engine import DiagnosisEngine
from deadman.diagnose.gemini import GeminiClient
from deadman.evidence.model import Evidence, Method, Observation

# A real fault with no cause anywhere in the evidence, paired with a healthy
# surface. The interesting result is not whether the model answers. It is
# whether it invents a cause for the first one, or correlates it with the
# second because the two arrived together.
EVIDENCE = [
    Evidence(
        surface="cron:morning-brief",
        observation=Observation.FAULT,
        method=Method.LOCAL_ARTIFACT,
        summary="no brief sent in 218.4h (window 30h, ~9 missed)",
        source="/var/log/deadman/morning-brief.jsonl",
        detail={
            "age_hours": 218.4,
            "row_count": 412,
            "last_send_at": "2026-08-01T11:02:00+00:00",
        },
    ),
    Evidence(
        surface="host:disk/",
        observation=Observation.HEALTHY,
        method=Method.LOCAL_ARTIFACT,
        summary="41.2GB free, 9 days of runway",
        source="statvfs:/",
        detail={"free_gb": 41.2, "slope_gb_per_day": -4.1, "runway_days": 8.8},
    ),
]

_REQUIRED_ENV = (
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
)


def main() -> int:
    missing = [name for name in _REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        print("missing environment: " + ", ".join(missing), file=sys.stderr)
        print("see docs/gemini-verification.md", file=sys.stderr)
        return 2

    location = os.environ["GOOGLE_CLOUD_LOCATION"]
    if location != "global":
        # Not fatal: the id is overridable and a future model may be regional.
        # But this is the exact wrong turn the docs warn about, so say so.
        print(
            f"warning: GOOGLE_CLOUD_LOCATION={location!r}, but gemini-3.5-flash "
            "is served only from 'global' and 404s elsewhere",
            file=sys.stderr,
        )

    diagnosis = DiagnosisEngine(client=GeminiClient()).diagnose(EVIDENCE)

    print("model      :", getattr(diagnosis, "model", "?"))
    print("confidence :", getattr(diagnosis, "confidence", "?"))
    print("hypothesis :", getattr(diagnosis, "hypothesis", "?"))
    print("cites      :", getattr(diagnosis, "evidence_ids", "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
