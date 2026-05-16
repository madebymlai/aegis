from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import DataConfig, redact_text, resolve_secret_refs


class RemoteDataPullError(ValueError):
    def __init__(self, source: str, message: str) -> None:
        self.source = source
        super().__init__(f"Failed to pull {source} data: {message}")


def load_market_data(config: DataConfig) -> pd.DataFrame:
    source = config.source.lower()
    if source == "synthetic":
        return _synthetic_ohlcv(config)
    if source == "csv":
        if config.path is None:
            raise ValueError("data.path is required for csv source")
        return _read_csv(config.path)
    if source == "yfinance":
        return _pull_remote(vbt.YFData, config).get()
    if source == "binance":
        return _pull_remote(vbt.BinanceData, config).get()
    if source == "ccxt":
        return _pull_remote(vbt.CCXTData, config).get()
    raise ValueError(f"Unsupported data source: {config.source}")


def close_from_ohlcv(data: pd.DataFrame) -> pd.Series | pd.DataFrame:
    return feature_from_ohlcv(data, "Close")


def high_from_ohlcv(data: pd.DataFrame) -> pd.Series | pd.DataFrame:
    return feature_from_ohlcv(data, "High")


def low_from_ohlcv(data: pd.DataFrame) -> pd.Series | pd.DataFrame:
    return feature_from_ohlcv(data, "Low")


def feature_from_ohlcv(data: pd.DataFrame, feature: str) -> pd.Series | pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        if feature in data.columns.get_level_values(-1):
            return data.xs(feature, axis=1, level=-1)
        if feature in data.columns.get_level_values(0):
            return data.xs(feature, axis=1, level=0)
    if feature in data.columns:
        return data[feature]
    raise ValueError(f"Data must contain a {feature} column")


def _read_csv(path: str) -> pd.DataFrame:
    frame = pd.read_csv(Path(path), index_col=0, parse_dates=True)
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame


def _pull_remote(data_cls, config: DataConfig):
    wrapper_kwargs, wrapper_secrets = resolve_secret_refs(
        config.wrapper_kwargs,
        "data.wrapper_kwargs",
    )
    provider_kwargs, provider_secrets = resolve_secret_refs(
        config.provider_kwargs,
        "data.provider_kwargs",
    )
    execution_kwargs, execution_secrets = resolve_secret_refs(
        config.execution_kwargs,
        "data.execution_kwargs",
    )
    secrets = wrapper_secrets + provider_secrets + execution_secrets
    error_message = None
    try:
        return data_cls.pull(
            config.symbols,
            start=config.start,
            end=config.end,
            timeframe=config.timeframe,
            missing_index=config.missing_index,
            missing_columns=config.missing_columns,
            tz_localize=config.tz_localize,
            tz_convert=config.tz_convert,
            wrapper_kwargs=wrapper_kwargs,
            execute_kwargs=execution_kwargs,
            **provider_kwargs,
        )
    except Exception as error:
        error_message = redact_text(str(error), secrets)
    raise RemoteDataPullError(config.source, error_message)


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
        frame.columns = pd.MultiIndex.from_product(
            [[symbol], frame.columns], names=["symbol", "feature"]
        )
        frames.append(frame)
    return pd.concat(frames, axis=1)
