"""Fail-closed validator for signed target-weight frames.

A **Strategy** speaks final **signed** target weights (positive = long, negative =
short); there is nothing left to normalize, so this module neither sizes nor mutates
weights. It only aligns the frame to the close columns and gates each rebalance row
against the run-level **gross** cap (``Σ|wᵢ| ≤ gross_cap``) before simulation. The
``net_cap`` / sign-consistency guards land in later slices.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STRATEGY_ALLOCATION_OUTPUTS: frozenset[str] = frozenset(
    {"active", "scores", "ranks", "target_weights"}
)

_GROSS_TOLERANCE = 1e-9


def validate_signed_target_weights(
    target_weights: pd.DataFrame,
    *,
    close_columns: pd.Index,
    gross_cap: float,
) -> pd.DataFrame:
    """Align a signed target-weight frame and enforce ``Σ|wᵢ| ≤ gross_cap`` fail-closed.

    Signed weights are admitted unchanged (negative = short). Every decided rebalance
    row (a row with at least one non-NaN weight) must satisfy ``Σ|wᵢ| ≤ gross_cap``;
    an all-NaN row is a no-rebalance and is left untouched.
    """
    if gross_cap <= 0:
        raise ValueError(f"gross_cap must be > 0; got {gross_cap!r}")

    aligned = _reindex_to_close_columns(target_weights, close_columns)
    values = aligned.to_numpy(dtype=float, copy=False)
    if values.size:
        decided = values[~np.isnan(values).all(axis=1)]
        if decided.size:
            gross = np.nansum(np.abs(decided), axis=1)
            if (gross > gross_cap + _GROSS_TOLERANCE).any():
                offending = float(gross.max())
                raise ValueError(
                    f"target_weights gross exposure Σ|wᵢ| {offending} "
                    f"exceeds gross_cap {gross_cap}"
                )
    return aligned


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
