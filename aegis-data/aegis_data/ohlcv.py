"""The Bar→OHLCV frame projection — the single home for the Catalog column shape.

Shared by the catalog port's window read, the continuous-future composer,
and the marking value object's frame projection; it sits below all of them so
none re-derives the column shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd


def bars_to_ohlcv(bars: Sequence[Any]) -> pd.DataFrame:
    """Project native ``Bar``\\ s into the Catalog OHLCV frame (UTC-naive index,
    float columns)."""
    rows: dict[str, list[float]] = {
        "Open": [],
        "High": [],
        "Low": [],
        "Close": [],
        "Volume": [],
    }
    index: list[pd.Timestamp] = []
    for bar in bars:
        index.append(pd.Timestamp(bar.ts_event, tz="UTC").tz_localize(None))
        rows["Open"].append(float(bar.open.as_double()))
        rows["High"].append(float(bar.high.as_double()))
        rows["Low"].append(float(bar.low.as_double()))
        rows["Close"].append(float(bar.close.as_double()))
        rows["Volume"].append(float(bar.volume.as_double()))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index)).sort_index()


__all__ = ["bars_to_ohlcv"]
