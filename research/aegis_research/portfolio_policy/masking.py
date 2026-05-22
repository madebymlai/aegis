from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

SYMBOL_LEVEL = "symbol"


def apply_executable_mask_and_terminal_liquidation(
    allocations: pd.DataFrame,
    *,
    market_index: pd.Index | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if allocations.empty or len(allocations.columns) == 0:
        return allocations.copy(), _empty_diagnostics(allocations.columns)

    executable = _next_open_executable_mask(allocations.index, market_index)
    masked = allocations.copy().astype(float)
    non_executable_rows = ~executable
    if non_executable_rows.any():
        masked.iloc[non_executable_rows.to_numpy(), :] = np.nan
    masked.iloc[-1, :] = 0.0
    diagnostics = _diagnostics(allocations, executable)
    return masked, diagnostics


def _next_open_executable_mask(
    index: pd.Index,
    market_index: pd.Index | None,
) -> pd.Series:
    executable = pd.Series(True, index=index)
    if market_index is None or len(index) == 0:
        return executable
    market_positions = pd.Series(range(len(market_index)), index=market_index)
    try:
        positions = market_positions.loc[index].to_numpy()
    except KeyError as error:
        raise ValueError(
            "portfolio market_index must contain all allocation rows"
        ) from error
    if len(index) < 2:
        return executable
    contiguous = positions[1:] == positions[:-1] + 1
    executable.iloc[1:] = contiguous
    return executable


def _diagnostics(
    allocations: pd.DataFrame,
    executable: pd.Series,
) -> dict[str, Any]:
    non_executable_count = int((~executable).sum())
    return {
        "non_executable_rows": non_executable_count,
        "non_executable_by_symbol": _per_symbol_non_executable(
            allocations, executable
        ),
        "terminal_liquidation": True,
    }


def _per_symbol_non_executable(
    allocations: pd.DataFrame,
    executable: pd.Series,
) -> dict[str, int]:
    columns = allocations.columns
    non_exec_count = int((~executable).sum())
    if isinstance(columns, pd.MultiIndex) and SYMBOL_LEVEL in columns.names:
        symbols = columns.get_level_values(SYMBOL_LEVEL)
        return {str(symbol): non_exec_count for symbol in dict.fromkeys(symbols)}
    return {str(column): non_exec_count for column in columns}


def _empty_diagnostics(columns: pd.Index) -> dict[str, Any]:
    return {
        "non_executable_rows": 0,
        "non_executable_by_symbol": {str(column): 0 for column in columns},
        "terminal_liquidation": True,
    }
