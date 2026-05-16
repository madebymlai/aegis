from __future__ import annotations

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import IndicatorConfig


def build_indicators(close: pd.Series | pd.DataFrame, config: IndicatorConfig) -> pd.DataFrame:
    indicator_frames: list[pd.DataFrame] = []

    close_df = close.to_frame() if isinstance(close, pd.Series) else close
    for window in config.returns:
        indicator_frames.append(_with_indicator_name(close_df.pct_change(window), f"ret_{window}"))

    for window in config.moving_average_windows:
        ma = vbt.MA.run(close_df, window=window, hide_params=True).ma
        distance = close_df / ma - 1
        indicator_frames.append(_with_indicator_name(distance, f"ma_dist_{window}"))

    for window in config.volatility_windows:
        vol = close_df.pct_change().rolling(window).std()
        indicator_frames.append(_with_indicator_name(vol, f"vol_{window}"))

    for window in config.rsi_windows:
        rsi = vbt.RSI.run(close_df, window=window, hide_params=True).rsi / 100.0
        indicator_frames.append(_with_indicator_name(rsi, f"rsi_{window}"))

    indicators = pd.concat(indicator_frames, axis=1).sort_index(axis=1)
    indicators.columns = [
        "__".join(map(str, col)) if isinstance(col, tuple) else str(col)
        for col in indicators.columns
    ]
    return indicators.replace([float("inf"), float("-inf")], pd.NA)


def _with_indicator_name(frame: pd.DataFrame, indicator_name: str) -> pd.DataFrame:
    out = frame.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = pd.MultiIndex.from_tuples(
            [(indicator_name, *col) for col in out.columns],
            names=["indicator", *out.columns.names],
        )
    else:
        out.columns = pd.MultiIndex.from_product(
            [[indicator_name], out.columns],
            names=["indicator", "symbol"],
        )
    return out
