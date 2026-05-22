from __future__ import annotations

import numpy as np
import pandas as pd

STRATEGY_ALLOCATION_OUTPUTS: frozenset[str] = frozenset(
    {"active", "scores", "ranks", "target_weights"}
)
LONG_ONLY = "longonly"


def convert_to_allocations(
    component_output: pd.DataFrame,
    declared_shape: str,
    *,
    close_columns: pd.Index,
    target_exposure_cap: float,
    direction: str = LONG_ONLY,
) -> pd.DataFrame:
    if direction != LONG_ONLY:
        raise ValueError(
            f"portfolio policy supports direction={LONG_ONLY!r} only; got {direction!r}"
        )
    if declared_shape not in STRATEGY_ALLOCATION_OUTPUTS:
        raise ValueError(
            f"unsupported declared_shape {declared_shape!r}; "
            f"registered shapes are {sorted(STRATEGY_ALLOCATION_OUTPUTS)}"
        )
    if target_exposure_cap <= 0:
        raise ValueError(
            f"target_exposure_cap must be > 0; got {target_exposure_cap!r}"
        )

    aligned = _reindex_to_close_columns(component_output, close_columns)

    if declared_shape == "target_weights":
        return _validate_target_weights(aligned, target_exposure_cap)
    if declared_shape == "active":
        return _convert_active(aligned, target_exposure_cap)
    return _convert_scores_or_ranks(aligned, target_exposure_cap)


def _reindex_to_close_columns(
    frame: pd.DataFrame,
    close_columns: pd.Index,
) -> pd.DataFrame:
    frame_keys = set(frame.columns)
    close_keys = set(close_columns)
    missing = sorted(map(repr, close_keys - frame_keys))
    if missing:
        raise ValueError(
            f"component output is missing columns required by close_columns: {missing}"
        )
    extra = sorted(map(repr, frame_keys - close_keys))
    if extra:
        raise ValueError(
            f"component output has columns not present in close_columns: {extra}"
        )
    aligned = frame.reindex(columns=close_columns)
    if not aligned.columns.equals(close_columns):
        raise ValueError(
            "component output columns do not match close_columns after reindex"
        )
    return aligned


def _validate_target_weights(
    frame: pd.DataFrame,
    target_exposure_cap: float,
) -> pd.DataFrame:
    values = frame.to_numpy(dtype=float, copy=True)
    if values.size == 0:
        return frame.astype(float)
    row_has_value = ~np.isnan(values).all(axis=1)
    decided = values[row_has_value]
    if decided.size:
        if np.any(np.nan_to_num(decided, nan=0.0) < 0):
            raise ValueError(
                "target_weights contains negative values; longonly contract requires weights >= 0"
            )
        row_sums = np.nansum(decided, axis=1)
        tolerance = 1e-9
        if (row_sums > target_exposure_cap + tolerance).any():
            offending = float(row_sums.max())
            raise ValueError(
                f"target_weights row sum {offending} exceeds target_exposure_cap {target_exposure_cap}"
            )
    return frame.astype(float)


def _convert_active(
    frame: pd.DataFrame,
    target_exposure_cap: float,
) -> pd.DataFrame:
    decided = frame.notna().to_numpy()
    selected = _coerce_active_to_bool(frame).to_numpy()
    selected = selected & decided
    return _equal_weight_from_mask(
        decided_row_mask=decided.any(axis=1),
        selection_mask=selected,
        index=frame.index,
        columns=frame.columns,
        target_exposure_cap=target_exposure_cap,
    )


def _convert_scores_or_ranks(
    frame: pd.DataFrame,
    target_exposure_cap: float,
) -> pd.DataFrame:
    selected = frame.notna().to_numpy()
    return _equal_weight_from_mask(
        decided_row_mask=selected.any(axis=1),
        selection_mask=selected,
        index=frame.index,
        columns=frame.columns,
        target_exposure_cap=target_exposure_cap,
    )


def _coerce_active_to_bool(frame: pd.DataFrame) -> pd.DataFrame:
    values = frame.to_numpy()
    bool_values = np.where(pd.isna(values), False, values).astype(bool)
    return pd.DataFrame(bool_values, index=frame.index, columns=frame.columns)


def _equal_weight_from_mask(
    *,
    decided_row_mask: np.ndarray,
    selection_mask: np.ndarray,
    index: pd.Index,
    columns: pd.Index,
    target_exposure_cap: float,
) -> pd.DataFrame:
    allocations = np.full(selection_mask.shape, np.nan, dtype=float)
    decided_rows = np.where(decided_row_mask)[0]
    counts = selection_mask.sum(axis=1)
    for row_idx in decided_rows:
        n_selected = counts[row_idx]
        if n_selected == 0:
            allocations[row_idx, :] = 0.0
        else:
            per_symbol = target_exposure_cap / n_selected
            allocations[row_idx, :] = np.where(
                selection_mask[row_idx], per_symbol, 0.0
            )
    return pd.DataFrame(allocations, index=index, columns=columns)
