"""Aegis Historical Store Read adapter for RD market data."""

from __future__ import annotations

import pandas as pd
from aegis_data.store import NativeBarsRequest, read_native_bars_request
from aegis_data.yfinance import YFinanceLocator, pull_yfinance_native_bars
from aegis_runtime import ListedRef

from research.aegis_research.configuration import (
    DataConfig,
    SymbolSpec,
    store_gap_fill_provider,
)
from research.aegis_research.market_data.adapters._support import (
    index_evidence,
    native_from_array_dict,
    native_index,
)
from research.aegis_research.market_data.contracts import MarketDataAdapterResult


def load_store_source(config: DataConfig) -> MarketDataAdapterResult:
    """Load RD cash/listed panels from aegis-data Covered History."""
    refs = tuple(_listed_ref(symbol) for symbol in config.symbols)
    request = NativeBarsRequest(
        refs=refs,
        arrays=config.effective_arrays,
        timeframe=config.timeframe,
        start=_required_window_edge(config.start, "start"),
        end=_required_window_edge(config.end, "end"),
    )
    provider = store_gap_fill_provider(config.provider_kwargs)
    _pull_missing_native_bars(config, refs=refs, provider=provider)
    frames = read_native_bars_request(request)
    arrays = _array_panels(config, refs=refs, frames=frames)
    native_data = native_from_array_dict(arrays, config)
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={"provider_class": "aegis_data.yfinance"},
        evidence=index_evidence(native_index(native_data), source="aegis_data_store"),
        provider_metadata={"source": "aegis_data_store", "gap_fill_provider": provider},
    )


def _pull_missing_native_bars(
    config: DataConfig,
    *,
    refs: tuple[ListedRef, ...],
    provider: str,
) -> None:
    if provider != "yfinance":
        raise ValueError(f"unsupported store gap-fill provider {provider!r}")
    for symbol, ref in zip(config.symbols, refs, strict=True):
        pull_yfinance_native_bars(
            NativeBarsRequest(
                refs=(ref,),
                arrays=config.effective_arrays,
                timeframe=config.timeframe,
                start=_required_window_edge(config.start, "start"),
                end=_required_window_edge(config.end, "end"),
            ),
            YFinanceLocator(symbol.ticker),
        )


def _listed_ref(symbol: SymbolSpec) -> ListedRef:
    if symbol.is_future:
        raise ValueError("store source currently supports listed instruments only")
    if symbol.figi is None:
        raise ValueError(f"store source requires figi for symbol {symbol.ticker!r}")
    return ListedRef(symbol.figi)


def _required_window_edge(value: str | None, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} is required for store source")
    return value


def _array_panels(
    config: DataConfig,
    *,
    refs: tuple[ListedRef, ...],
    frames: dict[ListedRef, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    panels: dict[str, pd.DataFrame] = {}
    for array in config.effective_arrays:
        panels[array] = pd.DataFrame(
            {
                symbol.ticker: frames[ref][array]
                for symbol, ref in zip(config.symbols, refs, strict=True)
            }
        )
    return panels


__all__ = ["load_store_source"]
