"""Co-occurrence: the deterministic half, and how little it is allowed to mean.

Graph-based monitoring answers "what else does this affect?" by walking a
lineage graph somebody declared. Across a laptop volume, a phone relay and a
third-party scheduler there is no such graph, nobody is going to write one, and
the surfaces share no schema to build it from. So the relationship has to be
inferred, and this module is the cheap first step of inferring it.

**What co-occurrence actually establishes: almost nothing.** Every probe in a
sweep runs within milliseconds of every other, so two faults share a
``read_at`` whether or not they share a cause. Worse, ``read_at`` is when *we
looked*, not when the fault began — a disk that filled at 02:00 and a post that
died at 02:04 are read simultaneously at 03:00. Treating that timestamp
agreement as evidence of a relationship would be numerology.

So the window does one job: it decides which faults are worth *asking* about.
It proposes; the evidence disposes (:mod:`deadman.correlate.engine`). Nothing
here contributes to correlation confidence, because nothing here is a reason to
believe anything.

Two rules do the real work.

**A candidate needs two faulting surfaces.** Not two rows — two *surfaces*. One
surface failing twice is one surface failing twice, and a correlation is a
claim about a relationship between different things.

**Blindness is never the second leg.** An ``UNOBSERVABLE`` row beside a lone
fault does not make a candidate, however suggestive the coincidence looks. A
surface we could not see cannot corroborate anything, and inferring a shared
cause from an absence of evidence is precisely the substitution this codebase
exists to prevent. Blind rows are carried as *context* instead: shown to the
model, which is instructed that blind is not healthy, and accounted for in the
report, which may not quietly drop them.
"""

from __future__ import annotations

from dataclasses import dataclass

from deadman.evidence.model import Evidence, Observation

#: Five minutes. Wide enough for collectors pushing on their own schedules from
#: different hosts, narrow enough that this morning's disk fault does not get
#: offered alongside this evening's publish failure. Widening it costs little,
#: because a wider window only proposes more candidates for the evidence to
#: reject — the gate that matters is not this one.
DEFAULT_WINDOW_SECONDS = 300.0


@dataclass(frozen=True)
class Candidate:
    """Faults close enough in time to be worth one question.

    Deliberately not called an incident. An incident is something the evidence
    earned; this is a set of rows that happened to be read at similar times.
    """

    faults: tuple[Evidence, ...]
    """Two or more surfaces in ``FAULT``, oldest read first. The legs."""

    context: tuple[Evidence, ...]
    """Blind rows in the same window. Never legs, never dropped."""

    @property
    def span(self) -> tuple[str, ...]:
        """The distinct faulting surfaces, sorted. Order-independent so two
        sweeps that found the same trouble compare equal."""
        return tuple(sorted({e.surface for e in self.faults}))

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        """Everything the candidate covers — what gets handed to the model."""
        return self.faults + self.context


def _sorted(evidence: list[Evidence]) -> list[Evidence]:
    """Stable regardless of how the sweep happened to order its probes. Surface
    breaks ties so two rows read in the same millisecond do not flap."""
    return sorted(evidence, key=lambda e: (e.read_at, e.surface))


def _clusters(faults: list[Evidence], window_seconds: float) -> list[list[Evidence]]:
    """Chain faults whose consecutive gap fits inside the window.

    Single linkage, so a run of overlapping windows joins into one cluster
    rather than being cut at an arbitrary origin. That is permissive, and
    permissive is right here: over-grouping costs one rejected candidate, while
    under-grouping hides the cascade this task exists to find.
    """
    groups: list[list[Evidence]] = []
    for one in faults:
        if groups and (one.read_at - groups[-1][-1].read_at).total_seconds() <= window_seconds:
            groups[-1].append(one)
        else:
            groups.append([one])
    return groups


def candidates(
    evidence: list[Evidence], *, window_seconds: float = DEFAULT_WINDOW_SECONDS
) -> list[Candidate]:
    """Every group of concurrent faults spanning more than one surface."""
    rows = _sorted(evidence)
    faults = [e for e in rows if e.observation is Observation.FAULT]
    blind = [e for e in rows if e.observation is Observation.UNOBSERVABLE]

    found = []
    for group in _clusters(faults, window_seconds):
        if len({e.surface for e in group}) < 2:
            continue
        found.append(
            Candidate(
                faults=tuple(group),
                context=tuple(_nearby(blind, group, window_seconds)),
            )
        )
    return found


def _nearby(blind: list[Evidence], group: list[Evidence], window_seconds: float) -> list[Evidence]:
    start, end = group[0].read_at, group[-1].read_at
    return [
        e
        for e in blind
        if (e.read_at - end).total_seconds() <= window_seconds
        and (start - e.read_at).total_seconds() <= window_seconds
    ]
