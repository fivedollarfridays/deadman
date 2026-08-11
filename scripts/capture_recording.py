#!/usr/bin/env python3
"""Capture a real Gemini response into the recording format the tests replay.

The recordings in ``tests/recorded/`` were authored against the response
contract rather than captured, because for most of this sprint no GCP
credentials existed. Authored fixtures prove the parser handles a shape we
invented. Only a capture proves a model actually produces it.

This writes the same envelope the loader already reads, with ``captured``
set to ``true``, so nothing downstream changes: the engine only ever sees a
string.

    python scripts/capture_recording.py bundle-disk-cascade captured-disk-cascade

Requires the live Gemini environment from ``docs/gemini-verification.md``,
including ``GOOGLE_CLOUD_LOCATION=global``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from recordings import RECORDED, load_bundle  # noqa: E402

from deadman.diagnose.gemini import DEFAULT_TEMPERATURE, GeminiClient  # noqa: E402
from deadman.diagnose.prompt import PROMPT_VERSION, render_prompt  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="capture-recording", description=__doc__)
    parser.add_argument("bundle", help="bundle name, e.g. bundle-disk-cascade")
    parser.add_argument("out", help="recording name to write, without .json")
    parser.add_argument("--note", default="", help="what this recording is for")
    args = parser.parse_args(argv)

    evidence = load_bundle(args.bundle)
    client = GeminiClient()
    response = client.complete(render_prompt(evidence))

    envelope = {
        "note": args.note or f"Real capture against {args.bundle}.",
        "captured": True,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "bundle": args.bundle,
        "model": client.model,
        "temperature": DEFAULT_TEMPERATURE,
        "prompt_version": PROMPT_VERSION,
        "response": response,
    }

    path = RECORDED / f"{args.out}.json"
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path} ({len(response)} chars from {client.model})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
