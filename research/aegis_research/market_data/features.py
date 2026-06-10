"""Public feature accessors over loaded market data.

The single home for the OHLCV feature accessors callers reach for
(`feature_from_ohlcv`, `close/high/low_from_ohlcv`) and the experiment
feature-requirement helpers. Panel mechanics live in :mod:`panels`; this
module is the caller-facing surface the facade re-exports.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from research.aegis_research.configuration import SignalConfig
from research.aegis_research.market_data import panels as _panels
from research.aegis_research.market_data.contracts import MarketDataResult


def close_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "Close")


def high_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "High")


def low_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "Low")


def feature_from_ohlcv(data: Any, feature: str) -> pd.DataFrame:
    if isinstance(data, MarketDataResult):
        data.assert_usable()
        loaded = tuple(data.metadata.get("loaded_arrays", ()))
        if loaded and feature not in loaded:
            raise ValueError(f"market data feature {feature!r} was not loaded for this run")
        return _panels.canonical_feature_panel(data.native_data, feature)
    if hasattr(data, "get") and not isinstance(data, pd.DataFrame):
        return _panels.feature_panel(data, feature, role=feature)
    return _panels.feature_from_frame(data, feature)


def required_ohlcv_features() -> tuple[str, ...]:
    return ("Close",)


def required_experiment_ohlcv_features(
    signal_config: SignalConfig | None = None,
) -> tuple[str, ...]:
    features = list(required_ohlcv_features())
    signal_config = signal_config or SignalConfig()
    if signal_config.execution_timing == "next_open" and "Open" not in features:
        features.append("Open")
    return tuple(features)
