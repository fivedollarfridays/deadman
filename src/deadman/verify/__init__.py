"""Verifying the monitor rather than the estate.

Everything under :mod:`deadman.probes` asks whether some surface is healthy.
This package asks the prior question — is anyone still watching, and is what
they last said recent enough to mean anything — because once evidence travels
over a wire, an empty board has two readings and only one of them is good
news. :mod:`deadman.self_check` makes the same argument about deadman's own
sweeps; this package makes it about the collectors that feed them.
"""

from __future__ import annotations

from deadman.verify.collector_liveness import (
    CollectorReport,
    LivenessReport,
    assess,
    assess_collector,
    collector_surface,
)
from deadman.verify.expectations import (
    CollectorExpectation,
    ExpectationError,
    load_expectations,
    parse_expectations,
)

__all__ = [
    "CollectorExpectation",
    "CollectorReport",
    "ExpectationError",
    "LivenessReport",
    "assess",
    "assess_collector",
    "collector_surface",
    "load_expectations",
    "parse_expectations",
]
