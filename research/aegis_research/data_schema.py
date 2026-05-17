from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

OHLC_FEATURES = ("Close", "High", "Low", "Open")


def ohlc_availability(data: pd.DataFrame) -> dict[str, bool]:
    if isinstance(data.columns, pd.MultiIndex):
        levels = set(map(str, data.columns.get_level_values(-1))) | set(
            map(str, data.columns.get_level_values(0))
        )
        return {feature: feature in levels for feature in OHLC_FEATURES}
    columns = set(map(str, data.columns))
    return {feature: feature in columns for feature in OHLC_FEATURES}


def table_shape(data: pd.DataFrame) -> dict[str, int]:
    return {"rows": len(data), "columns": len(data.columns)}


def index_identity(index: pd.Index) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    start = None
    end = None
    for value in index:
        text = str(value)
        if count:
            digest.update(b"\n")
        digest.update(text.encode())
        if start is None:
            start = text
        end = text
        count += 1
    return {
        "count": count,
        "start": start,
        "end": end,
        "hash": digest.hexdigest(),
    }
