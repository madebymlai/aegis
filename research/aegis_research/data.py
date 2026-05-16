from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import DataConfig, redact_text, resolve_secret_refs
from research.aegis_research.data_schema import ohlc_availability, table_shape


class RemoteDataPullError(ValueError):
    def __init__(self, source: str, message: str) -> None:
        self.source = source
        super().__init__(f"Failed to pull {source} data: {message}")


@dataclass(frozen=True)
class MarketDataResult:
    data: pd.DataFrame
    metadata: dict[str, Any]
    native_object: Any | None = None
    known_secrets: tuple[str, ...] = ()


def load_market_data(config: DataConfig) -> pd.DataFrame:
    return load_market_data_result(config).data


def load_market_data_result(config: DataConfig) -> MarketDataResult:
    source = config.source.lower()
    if source == "synthetic":
        data = _synthetic_ohlcv(config)
        return MarketDataResult(data=data, metadata=_data_metadata(config, data))
    if source == "csv":
        if config.path is None:
            raise ValueError("data.path is required for csv source")
        data = _read_csv(config.path)
        return MarketDataResult(data=data, metadata=_data_metadata(config, data))
    if source == "yfinance":
        native, known_secrets = _pull_remote(vbt.YFData, config)
        data = native.get()
        return MarketDataResult(
            data=data,
            metadata=_data_metadata(config, data, native),
            native_object=native,
            known_secrets=known_secrets,
        )
    if source == "binance":
        native, known_secrets = _pull_remote(vbt.BinanceData, config)
        data = native.get()
        return MarketDataResult(
            data=data,
            metadata=_data_metadata(config, data, native),
            native_object=native,
            known_secrets=known_secrets,
        )
    if source == "ccxt":
        native, known_secrets = _pull_remote(vbt.CCXTData, config)
        data = native.get()
        return MarketDataResult(
            data=data,
            metadata=_data_metadata(config, data, native),
            native_object=native,
            known_secrets=known_secrets,
        )
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
        return (
            data_cls.pull(
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
            ),
            tuple(secrets),
        )
    except Exception as error:
        error_message = redact_text(str(error), secrets)
    raise RemoteDataPullError(config.source, error_message)


def _data_metadata(
    config: DataConfig,
    data: pd.DataFrame,
    native_object: Any | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": config.source,
        "symbols": list(config.symbols),
        "timeframe": config.timeframe,
        "shape": table_shape(data),
        "ohlc_available": ohlc_availability(data),
        "index_start": str(data.index[0]) if len(data.index) else None,
        "index_end": str(data.index[-1]) if len(data.index) else None,
    }
    if native_object is not None:
        metadata["native_class"] = type(native_object).__name__
        metadata["provider_metadata"] = _safe_native_data_metadata(native_object)
    return metadata


def _safe_native_data_metadata(native_object: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for name in ("last_index", "delisted", "missing_index", "missing_columns", "tz_localize", "tz_convert"):
        if hasattr(native_object, name):
            metadata[name] = str(getattr(native_object, name))
    return metadata


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
