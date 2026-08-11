"""Cross-surface correlation: inferring the graph nobody wrote.

See :mod:`deadman.correlate.window` for what co-occurrence is allowed to mean
and :mod:`deadman.correlate.engine` for how a shared cause is earned from
evidence rather than traversed from a lineage graph that does not exist.
"""

from __future__ import annotations

from deadman.correlate.engine import Correlator
from deadman.correlate.incident import Basis, CorrelationStatus, Incident
from deadman.correlate.report import as_dict, render
from deadman.correlate.window import Candidate, candidates

__all__ = [
    "Basis",
    "Candidate",
    "CorrelationStatus",
    "Correlator",
    "Incident",
    "as_dict",
    "candidates",
    "render",
]
