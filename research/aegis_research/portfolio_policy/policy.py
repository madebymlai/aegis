"""Fail-closed validator for signed target-weight frames.

A **Strategy** speaks final **signed** target weights (positive = long, negative =
short); there is nothing left to normalize, so this module neither sizes nor mutates
weights. It only aligns the frame to the close columns and gates each rebalance row
against the run-level exposure caps before simulation: **gross** (``Σ|wᵢ| ≤ gross_cap``)
and **net** (``|Σwᵢ| ≤ net_cap``). A market-neutral book is ``net_cap ≈ 0``; net is the
only cap VBT cannot enforce natively, so this validator is its sole gate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STRATEGY_ALLOCATION_OUTPUTS: frozenset[str] = frozenset(
    {"active", "scores", "ranks", "target_weights"}
)

_EXPOSURE_TOLERANCE = 1e-9
# A run's declared Direction fixes the admissible sign of every emitted weight, mirroring
# VBT's ``Direction`` enum (the same string is passed to ``from_optimizer``). ``both``
# admits either sign; ``longonly``/``shortonly`` are the fail-closed sign guard that the
# gross/net caps cannot supply — a ``[+.5,+.5] → [-.5,+.5]`` flip keeps gross = 1 and
# net = 0, so only this sign check catches it.
_SIGN_GUARDS: dict[str, str] = {"longonly": "≥ 0", "shortonly": "≤ 0", "both": "any"}


def validate_signed_target_weights(
    target_weights: pd.DataFrame,
    *,
    close_columns: pd.Index,
    gross_cap: float,
    net_cap: float | None = None,
    direction: str = "both",
) -> pd.DataFrame:
    """Align a signed target-weight frame and enforce the exposure caps fail-closed.

    Signed weights are admitted unchanged (negative = short). Every decided rebalance
    row (a row with at least one non-NaN weight) must satisfy both the gross cap
    (``Σ|wᵢ| ≤ gross_cap``) and the net cap (``|Σwᵢ| ≤ net_cap``); an all-NaN row is a
    no-rebalance and is left untouched. ``net_cap`` defaults to ``gross_cap`` — a no-op,
    since ``|Σwᵢ| ≤ Σ|wᵢ| ≤ gross_cap`` always — so omitting it never tightens the gross
    gate. ``net_cap ≈ 0`` is market-neutral.

    ``direction`` is the run-level sign guard: ``longonly`` requires ``wᵢ ≥ 0``,
    ``shortonly`` requires ``wᵢ ≤ 0``, ``both`` admits either sign. It catches a sign-flip
    bug the caps miss (a ``[+.5,+.5] → [-.5,+.5]`` flip keeps gross = 1, net = 0).
    """
    if gross_cap <= 0:
        raise ValueError(f"gross_cap must be > 0; got {gross_cap!r}")
    if direction not in _SIGN_GUARDS:
        raise ValueError(
            f"direction must be one of {sorted(_SIGN_GUARDS)}; got {direction!r}"
        )
    if net_cap is None:
        net_cap = gross_cap

    aligned = _reindex_to_close_columns(target_weights, close_columns)
    values = aligned.to_numpy(dtype=float, copy=False)
    if values.size:
        decided = values[~np.isnan(values).all(axis=1)]
        if decided.size:
            _assert_sign_consistent(decided, direction)
            gross = np.nansum(np.abs(decided), axis=1)
            if (gross > gross_cap + _EXPOSURE_TOLERANCE).any():
                offending = float(gross.max())
                raise ValueError(
                    f"target_weights gross exposure Σ|wᵢ| {offending} "
                    f"exceeds gross_cap {gross_cap}"
                )
            net = np.abs(np.nansum(decided, axis=1))
            if (net > net_cap + _EXPOSURE_TOLERANCE).any():
                offending = float(net.max())
                raise ValueError(
                    f"target_weights net exposure |Σwᵢ| {offending} "
                    f"exceeds net_cap {net_cap}"
                )
    return aligned


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


def _reindex_to_close_columns(
    frame: pd.DataFrame,
    close_columns: pd.Index,
) -> pd.DataFrame:
    frame_keys = set(frame.columns)
    close_keys = set(close_columns)
    missing = sorted(map(repr, close_keys - frame_keys))
    if missing:
        raise ValueError(
            f"target_weights is missing columns required by close_columns: {missing}"
        )
    extra = sorted(map(repr, frame_keys - close_keys))
    if extra:
        raise ValueError(
            f"target_weights has columns not present in close_columns: {extra}"
        )
    aligned = frame.reindex(columns=close_columns)
    if not aligned.columns.equals(close_columns):
        raise ValueError(
            "target_weights columns do not match close_columns after reindex"
        )
    return aligned.astype(float)
