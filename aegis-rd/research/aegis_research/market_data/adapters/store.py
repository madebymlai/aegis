"""Aegis Historical Store Read adapter for RD market data."""

from __future__ import annotations

import pandas as pd
from aegis_data.store import NativeBarsRequest, read_native_bars_request
from aegis_runtime import ListedRef

from research.aegis_research.configuration import DataConfig, SymbolSpec
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
    frames = read_native_bars_request(request)
    arrays = _array_panels(config, refs=refs, frames=frames)
    native_data = native_from_array_dict(arrays, config)
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={"provider_class": None},
        evidence=index_evidence(native_index(native_data), source="aegis_data_store"),
        provider_metadata={"source": "aegis_data_store"},
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
