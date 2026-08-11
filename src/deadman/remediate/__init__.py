"""Remediation: deterministic actions, selected by the diagnosis.

The split this package exists to hold: **the model chooses, code acts.** The
diagnosis layer decides which evidence is causal — inference over messy
heterogeneous failure material, the thing a rule engine cannot do.
:mod:`~deadman.remediate.cause` reads what that evidence says using rules
written in advance, and :mod:`~deadman.remediate.registry` looks the answer up
in a closed table of functions that existed before the run.

No string a model produced is ever a key, an argument, or a body.
"""
