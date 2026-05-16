from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

OHLC_FEATURES = ("Close", "High", "Low", "Open")


def primary_series(values: pd.Series | pd.DataFrame, *, role: str) -> pd.Series:
    if isinstance(values, pd.Series):
        return values.rename(values.name or role)
    if values.empty or len(values.columns) == 0:
        raise ValueError(f"{role} data must contain at least one column")
    column = values.columns[0]
    return values.iloc[:, 0].rename(str(column))


def ohlc_availability(data: pd.DataFrame) -> dict[str, bool]:
    if isinstance(data.columns, pd.MultiIndex):
        levels = set(map(str, data.columns.get_level_values(-1))) | set(
            map(str, data.columns.get_level_values(0))
        )
        return {feature: feature in levels for feature in OHLC_FEATURES}
    columns = set(map(str, data.columns))
    return {feature: feature in columns for feature in OHLC_FEATURES}


def table_shape(data: pd.Series | pd.DataFrame) -> dict[str, int]:
    if isinstance(data, pd.Series):
        return {"rows": len(data), "columns": 1}
    return {"rows": len(data), "columns": len(data.columns)}


def index_identity(index: pd.Index) -> dict[str, Any]:
    values = [str(value) for value in index]
    digest = hashlib.sha256("\n".join(values).encode()).hexdigest()
    return {
        "count": len(index),
        "start": values[0] if values else None,
        "end": values[-1] if values else None,
        "hash": digest,
    }
