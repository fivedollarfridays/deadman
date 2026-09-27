"""The deploy pins the preview's public URL instead of trusting request headers.

Without ``DEADMAN_PUBLIC_URL`` the preview page builds ``og:url`` and
``og:image`` from the request's ``Host``. Cloud Run only routes a request
whose host is the service's, but pinning it at deploy makes the published
URLs a property of configuration rather than of whoever sent the request.
"""

from __future__ import annotations

import re
from pathlib import Path

_CLOUDBUILD = Path(__file__).resolve().parent.parent / "cloudbuild.yaml"


def _deploy_args() -> str:
    return "\n".join(
        line for line in _CLOUDBUILD.read_text().splitlines() if not line.lstrip().startswith("#")
    )


def test_the_deploy_pins_the_public_url_with_update_env_vars() -> None:
    args = _deploy_args()
    assert re.search(r"--update-env-vars=[^\n]*DEADMAN_PUBLIC_URL=\$\{_PUBLIC_URL\}", args)
    assert re.search(r"_PUBLIC_URL: https://\S+\.run\.app\s*$", args, re.MULTILINE)


def test_the_deploy_never_replaces_the_whole_environment() -> None:
    assert "--set-env-vars" not in _deploy_args()
