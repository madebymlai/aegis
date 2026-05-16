from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import IndicatorConfig
from research.aegis_research.data_schema import table_shape


@dataclass(frozen=True)
class IndicatorResult:
    frame: pd.DataFrame
    metadata: dict[str, object]


def build_indicators(close: pd.Series | pd.DataFrame, config: IndicatorConfig) -> pd.DataFrame:
    return build_indicator_result(close, config).frame


def build_indicator_result(close: pd.Series | pd.DataFrame, config: IndicatorConfig) -> IndicatorResult:
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
    frame = indicators.replace([float("inf"), float("-inf")], pd.NA)
    return IndicatorResult(
        frame=frame,
        metadata={
            "returns": list(config.returns),
            "moving_average_windows": list(config.moving_average_windows),
            "volatility_windows": list(config.volatility_windows),
            "rsi_windows": list(config.rsi_windows),
            "shape": table_shape(frame),
            "columns": list(map(str, frame.columns)),
        },
    )


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
