from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import DataConfig


def load_market_data(config: DataConfig) -> pd.DataFrame:
    source = config.source.lower()
    if source == "synthetic":
        return _synthetic_ohlcv(config)
    if source == "csv":
        if config.path is None:
            raise ValueError("data.path is required for csv source")
        return _read_csv(config.path)
    if source == "yfinance":
        data = vbt.YFData.pull(config.symbols, start=config.start, end=config.end, timeframe=config.timeframe)
        return data.get()
    if source == "binance":
        data = vbt.BinanceData.pull(
            config.symbols,
            start=config.start,
            end=config.end,
            timeframe=config.timeframe,
        )
        return data.get()
    if source == "ccxt":
        data = vbt.CCXTData.pull(
            config.symbols,
            start=config.start,
            end=config.end,
            timeframe=config.timeframe,
        )
        return data.get()
    raise ValueError(f"Unsupported data source: {config.source}")


def close_from_ohlcv(data: pd.DataFrame) -> pd.Series | pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(-1):
            return data.xs("Close", axis=1, level=-1)
        if "Close" in data.columns.get_level_values(0):
            return data.xs("Close", axis=1, level=0)
    if "Close" in data.columns:
        return data["Close"]
    raise ValueError("Data must contain a Close column")


def _read_csv(path: str) -> pd.DataFrame:
    frame = pd.read_csv(Path(path), index_col=0, parse_dates=True)
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame


def _synthetic_ohlcv(config: DataConfig) -> pd.DataFrame:
    rng = np.random.default_rng(config.seed)
    index = pd.date_range(
        config.start or "2020-01-01",
        periods=config.rows,
        freq=config.timeframe,
        tz="UTC",
        name="Open time",
    )
    frames = []
    for symbol_idx, symbol in enumerate(config.symbols):
        drift = 0.00015 + symbol_idx * 0.00003
        volatility = 0.015 + symbol_idx * 0.002
        returns = rng.normal(drift, volatility, size=config.rows)
        close = 100 * np.cumprod(1 + returns)
        spread = np.abs(rng.normal(0.002, 0.001, size=config.rows))
        open_ = close * (1 + rng.normal(0, 0.001, size=config.rows))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = rng.lognormal(mean=12, sigma=0.25, size=config.rows)
        frame = pd.DataFrame(
            {
                "Open": open_,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume,
            },
            index=index,
        )
        frame.columns = pd.MultiIndex.from_product([[symbol], frame.columns], names=["symbol", "feature"])
        frames.append(frame)
    return pd.concat(frames, axis=1)
