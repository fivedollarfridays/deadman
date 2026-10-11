"""The in-memory backend.

Every test in this repository runs against this one. That is deliberate and it
is the reason ``tests/test_store_contract.py`` parametrises rather than
targeting: a suite that only exercises the fast backend is a suite that only
proves the fast backend, and the deployed service runs the other one.

Nothing here persists. That is not a limitation to be fixed later, it is the
point — a test that can leave state behind is a test that can pass because of
the last one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from deadman.evidence.model import Evidence
from deadman.store.base import DEFAULT_HISTORY_LIMIT, absent, instant, row_id

SOURCE = "store:memory"


@dataclass
class InMemoryEvidenceStore:
    """An :class:`~deadman.store.base.EvidenceStore` held in a dict."""

    _rows: dict[str, list[Evidence]] = field(default_factory=dict, repr=False)
    _ids: set[str] = field(default_factory=set, repr=False)
    _alert_state: dict[str, str] = field(default_factory=dict, repr=False)

    def append(self, evidence: Evidence) -> None:
        identity = row_id(evidence)
        if identity in self._ids:
            return
        self._ids.add(identity)
        self._rows.setdefault(evidence.surface, []).append(evidence)

    def history(self, surface: str, limit: int = DEFAULT_HISTORY_LIMIT) -> list[Evidence]:
        if limit <= 0:
            return []
        ordered = sorted(self._rows.get(surface, ()), key=lambda e: instant(e.read_at))
        return ordered[-limit:]

    def latest(self, surface: str) -> Evidence:
        newest = self.history(surface, limit=1)
        return newest[0] if newest else absent(surface, SOURCE)

    def latest_per_surface(self) -> dict[str, Evidence]:
        return {surface: self.latest(surface) for surface in sorted(self._rows)}

    def load_alert_state(self, key: str) -> dict[str, Any] | None:
        stored = self._alert_state.get(key)
        return None if stored is None else json.loads(stored)

    def save_alert_state(self, key: str, record: Mapping[str, Any]) -> None:
        """Held as JSON text, not as the caller's object: a durable backend
        hands back a copy of what was serialised, and the backoff decision
        must not be able to pass here on aliasing it would not get there."""
        self._alert_state[key] = json.dumps(dict(record))
