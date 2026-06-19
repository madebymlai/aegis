"""Aegis Historical Store Read adapter for RD market data."""

from __future__ import annotations

import pandas as pd
from aegis_data.databento_pull import pull_databento_futures_bars
from aegis_data.store import NativeBarsRequest, read_native_bars_request
from aegis_data.yfinance import YFinanceLocator, pull_yfinance_native_bars
from aegis_runtime import FuturesRef, InstrumentRef, ListedRef

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
    """Load RD panels from aegis-data Covered History."""
    refs = tuple(_instrument_ref(config, symbol) for symbol in config.symbols)
    request = _native_bars_request(config, refs)
    provider = store_gap_fill_provider(config.provider)
    _pull_missing_native_bars(config, refs=refs, provider=provider)
    frames = read_native_bars_request(request)
    arrays = _array_panels(config, refs=refs, frames=frames)
    native_data = native_from_array_dict(arrays, config)
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={"provider_class": f"aegis_data.{provider}"},
        evidence=index_evidence(native_index(native_data), source="aegis_data_store"),
        provider_metadata={"source": "aegis_data_store", "gap_fill_provider": provider},
    )


def _pull_missing_native_bars(
    config: DataConfig,
    *,
    refs: tuple[InstrumentRef, ...],
    provider: str,
) -> None:
    for symbol, ref in zip(config.symbols, refs, strict=True):
        request = _native_bars_request(config, (ref,))
        if isinstance(ref, ListedRef) and provider == "yfinance":
            pull_yfinance_native_bars(request, YFinanceLocator(symbol.symbol_name))
            continue
        if isinstance(ref, FuturesRef) and provider == "databento":
            pull_databento_futures_bars(request)
            continue
        raise ValueError(f"unsupported store gap-fill provider {provider!r} for {ref!r}")


def _native_bars_request(config: DataConfig, refs: tuple[InstrumentRef, ...]) -> NativeBarsRequest:
    return NativeBarsRequest(
        refs=refs,
        arrays=config.effective_arrays,
        timeframe=config.timeframe,
        start=_required_window_edge(config.start, "start"),
        end=_required_window_edge(config.end, "end"),
    )


def _instrument_ref(config: DataConfig, symbol: SymbolSpec) -> InstrumentRef:
    if symbol.is_future:
        return _futures_ref(config, symbol)
    return _listed_ref(symbol)


def _listed_ref(symbol: SymbolSpec) -> ListedRef:
    if symbol.figi is None:
        raise ValueError(f"store source requires figi for symbol {symbol.symbol_name!r}")
    return ListedRef(symbol.figi)


def _futures_ref(config: DataConfig, symbol: SymbolSpec) -> FuturesRef:
    if config.dataset is None:
        raise ValueError("data.dataset is required for store futures")
    if symbol.root is None:
        raise ValueError("root is required for store futures")
    return FuturesRef(
        root=symbol.root,
        dataset=config.dataset,
        roll_rule=symbol.roll_rule,
        adjustment=symbol.adjustment,
    )


def _required_window_edge(value: str | None, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} is required for store source")
    return value


def _array_panels(
    config: DataConfig,
    *,
    refs: tuple[InstrumentRef, ...],
    frames: dict[InstrumentRef, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    panels: dict[str, pd.DataFrame] = {}
    for array in config.effective_arrays:
        panels[array] = pd.DataFrame(
            {
                symbol.symbol_name: frames[ref][array]
                for symbol, ref in zip(config.symbols, refs, strict=True)
            }
        )
    return panels


__all__ = ["load_store_source"]
