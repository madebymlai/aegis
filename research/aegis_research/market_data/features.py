"""Public Array accessors over loaded market data.

The single home for the OHLCV Array accessors callers reach for
(`array_from_ohlcv`, `close/high/low_from_ohlcv`) and the experiment
Array-requirement helpers. Panel mechanics live in :mod:`panels`; this
module is the caller-facing surface the facade re-exports.

``array_from_ohlcv`` is a pure resolver over native data / frames — no
usability guard, no ``assert_usable``, no ``MarketDataResult`` branch.
The resolver module is independent of the container types.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from research.aegis_research.configuration import SignalConfig
from research.aegis_research.market_data import panels as _panels


def close_from_ohlcv(data: Any) -> pd.DataFrame:
    return array_from_ohlcv(data, "Close")


def high_from_ohlcv(data: Any) -> pd.DataFrame:
    return array_from_ohlcv(data, "High")


def low_from_ohlcv(data: Any) -> pd.DataFrame:
    return array_from_ohlcv(data, "Low")


def array_from_ohlcv(data: Any, array: str) -> pd.DataFrame:
    """Extract a named Array panel from native data or a DataFrame.

    Dispatches on a ``.get()``-bearing object (native VBT data) or
    ``pd.DataFrame``. No usability guard or ``MarketDataResult`` coupling.
    """
    if hasattr(data, "get") and not isinstance(data, pd.DataFrame):
        return _panels.array_panel(data, array, role=array)
    return _panels.array_from_frame(data, array)


def required_ohlcv_arrays() -> tuple[str, ...]:
    return ("Close",)


def required_experiment_ohlcv_arrays(
    signal_config: SignalConfig | None = None,
) -> tuple[str, ...]:
    arrays = list(required_ohlcv_arrays())
    signal_config = signal_config or SignalConfig()
    if signal_config.execution_timing == "next_open" and "Open" not in arrays:
        arrays.append("Open")
    return tuple(arrays)
