"""Fail-closed validator for signed target-weight frames.

A **Strategy** speaks final **signed** target weights (positive = long, negative =
short); there is nothing left to normalize, so this module neither sizes nor mutates
weights. It only gates each rebalance row against the run-level exposure caps before
simulation: **gross** (``Σ|wᵢ| ≤ gross_cap``) and **net** (``|Σwᵢ| ≤ net_cap``). A
market-neutral book is ``net_cap ≈ 0``; net is the only cap VBT cannot enforce
natively, so this validator is its sole gate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_EXPOSURE_TOLERANCE = 1e-9
# A run's declared Direction fixes the admissible sign of every emitted weight, mirroring
# VBT's ``Direction`` enum (the same string is passed to ``from_optimizer``). ``both``
# admits either sign; ``longonly``/``shortonly`` are the fail-closed sign guard that the
# gross/net caps cannot supply — a ``[+.5,+.5] → [-.5,+.5]`` flip keeps gross = 1 and
# net = 0, so only this sign check catches it.
_SIGN_GUARDS: dict[str, str] = {"longonly": "≥ 0", "shortonly": "≤ 0", "both": "any"}


def assert_signed_allocations_within_caps(
    allocations: pd.DataFrame,
    *,
    gross_cap: float,
    net_cap: float | None = None,
    direction: str = "both",
) -> None:
    """Fail-closed gross/net/sign gate for a single-book or candidate-wide signed frame.

    Accepts plain symbol columns (one book) or a candidate-expanded MultiIndex frame with a
    ``symbol`` level; in the wide case each Candidate group is gated independently and a
    breaching Candidate is named in the error. Pure validation — it never mutates the frame.
    A market-neutral book is ``net_cap ≈ 0``; ``net_cap`` defaults to ``gross_cap`` (a no-op,
    since ``|Σwᵢ| ≤ Σ|wᵢ| ≤ gross_cap``). ``direction`` is the run-level sign guard
    (``longonly ⇒ wᵢ ≥ 0``, ``shortonly ⇒ wᵢ ≤ 0``, ``both`` admits either), catching a
    sign-flip the caps miss.
    """
    if gross_cap <= 0:
        raise ValueError(f"gross_cap must be > 0; got {gross_cap!r}")
    if direction not in _SIGN_GUARDS:
        raise ValueError(
            f"direction must be one of {sorted(_SIGN_GUARDS)}; got {direction!r}"
        )
    if net_cap is None:
        net_cap = gross_cap
    if allocations.empty or len(allocations.columns) == 0:
        return
    # Deferred import to break circular dependency: portfolios.py imports
    # allocation_policy at module level, so we import portfolios inside the call.
    from research.aegis_research.portfolios import SYMBOL_LEVEL

    _assert_sign_consistent(allocations.to_numpy(dtype=float, copy=False), direction)
    columns = allocations.columns
    if isinstance(columns, pd.MultiIndex) and SYMBOL_LEVEL in columns.names:
        candidate_levels = [name for name in columns.names if name != SYMBOL_LEVEL]
        grouper = candidate_levels[0] if len(candidate_levels) == 1 else candidate_levels
        gross = allocations.abs().T.groupby(level=grouper, sort=False).sum().T
        net = allocations.T.groupby(level=grouper, sort=False).sum().T.abs()
        _assert_candidate_cap(gross, gross_cap, "gross", "Σ|wᵢ|")
        _assert_candidate_cap(net, net_cap, "net", "|Σwᵢ|")
        return
    gross = allocations.abs().sum(axis=1)
    if (gross > gross_cap + _EXPOSURE_TOLERANCE).any():
        raise ValueError(
            f"gross exposure Σ|wᵢ| {float(gross.max())} exceeds gross_cap {gross_cap}"
        )
    net = allocations.sum(axis=1).abs()
    if (net > net_cap + _EXPOSURE_TOLERANCE).any():
        raise ValueError(
            f"net exposure |Σwᵢ| {float(net.max())} exceeds net_cap {net_cap}"
        )


def _assert_candidate_cap(
    per_candidate: pd.DataFrame, cap: float, name: str, expr: str
) -> None:
    """Raise, naming the worst-offending Candidate, when a per-Candidate cap is breached."""
    worst_per_candidate = per_candidate.max(axis=0)
    if (worst_per_candidate > cap + _EXPOSURE_TOLERANCE).any():
        offender = worst_per_candidate.idxmax()
        raise ValueError(
            f"candidate {offender!r} {name} exposure {expr} "
            f"{float(worst_per_candidate.max())} exceeds {name}_cap {cap}"
        )


def _assert_sign_consistent(decided: np.ndarray, direction: str) -> None:
    """Fail closed when a weight's sign contradicts the run's declared Direction."""
    if direction == "longonly":
        offenders = decided < -_EXPOSURE_TOLERANCE
    elif direction == "shortonly":
        offenders = decided > _EXPOSURE_TOLERANCE
    else:
        return
    if offenders.any():
        offending = float(decided[offenders][0])
        raise ValueError(
            f"target_weights has weight {offending} violating direction "
            f"{direction!r} (requires wᵢ {_SIGN_GUARDS[direction]})"
        )
