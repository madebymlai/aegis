"""Aegis Historical Store Read adapter for RD market data."""

from __future__ import annotations

import pandas as pd
from aegis_data.calendars import TradingCalendar
from aegis_data.coverage import GapFillProvider, ensure_native_bar_coverage
from aegis_data.store import NativeBarsRequest, read_native_bars_request
from aegis_runtime import FuturesRef, InstrumentRef, ListedRef

from research.aegis_research.configuration import (
    DataConfig,
    SymbolSpec,
    required_store_window_edge,
    store_gap_fill_provider,
)
from research.aegis_research.market_data.adapters._support import (
    index_evidence,
    native_from_array_dict,
    native_index,
)
from research.aegis_research.market_data.contracts import MarketDataAdapterResult


def load_store_source(config: DataConfig) -> MarketDataAdapterResult:
    """Load RD panels from aegis-data Covered History.

    A futures symbol may declare a second continuous series via ``pnl_adjustment``:
    the ``adjustment`` series drives the indicators (signal) and the ``pnl_adjustment``
    series is carried alongside as ``pnl_native_data`` for the portfolio to simulate
    P&L against.  Both modes derive from the same cached raw legs (the store keys by
    adjustment), so the second series adds no extra provider fetch.
    """
    signal_refs = tuple(_instrument_ref(config, symbol) for symbol in config.symbols)
    pnl_refs = tuple(_pnl_ref(config, symbol, signal) for symbol, signal in zip(config.symbols, signal_refs, strict=True))
    all_refs = signal_refs + tuple(ref for ref in pnl_refs if ref not in signal_refs)
    request = _native_bars_request(config, all_refs)
    provider = store_gap_fill_provider(config.provider)
    ensure_native_bar_coverage(
        request,
        provider=GapFillProvider(provider),
        locators=_provider_locators(config, signal_refs, pnl_refs),
    )
    frames = read_native_bars_request(request)
    native_data = native_from_array_dict(_array_panels(config, refs=signal_refs, frames=frames), config)
    pnl_native_data = (
        native_from_array_dict(_array_panels(config, refs=pnl_refs, frames=frames), config)
        if pnl_refs != signal_refs
        else None
    )
    return MarketDataAdapterResult(
        native_data=native_data,
        pnl_native_data=pnl_native_data,
        source_metadata={"provider_class": f"aegis_data.{provider}"},
        evidence=index_evidence(native_index(native_data), source="aegis_data_store"),
        provider_metadata={"source": "aegis_data_store", "gap_fill_provider": provider},
    )


def _pnl_ref(
    config: DataConfig, symbol: SymbolSpec, signal_ref: InstrumentRef
) -> InstrumentRef:
    """The P&L-series ref for a dual-adjustment future, else the signal ref itself.

    A future with ``pnl_adjustment`` resolves to a second ``FuturesRef`` differing only
    in adjustment (a distinct store key derived from the same raw legs); every other
    symbol reuses its signal ref, so the P&L panel spans the whole universe.
    """
    if symbol.is_future and symbol.pnl_adjustment is not None:
        return _futures_ref(config, symbol, adjustment=symbol.pnl_adjustment)
    return signal_ref


def _provider_locators(
    config: DataConfig,
    signal_refs: tuple[InstrumentRef, ...],
    pnl_refs: tuple[InstrumentRef, ...],
) -> dict[InstrumentRef, str]:
    # The P&L ref shares its symbol's locator: both modes pull from the same root.
    locators: dict[InstrumentRef, str] = {}
    for symbol, signal, pnl in zip(config.symbols, signal_refs, pnl_refs, strict=True):
        locators[signal] = symbol.symbol_name
        locators[pnl] = symbol.symbol_name
    return locators


def _native_bars_request(config: DataConfig, refs: tuple[InstrumentRef, ...]) -> NativeBarsRequest:
    # RD's listed universe is US-listed (yfinance) and its futures are CME (GLBX);
    # both expect bars on the XNYS calendar.
    return NativeBarsRequest(
        refs=refs,
        arrays=config.effective_arrays,
        timeframe=config.timeframe,
        start=required_store_window_edge(config.start, "start"),
        end=required_store_window_edge(config.end, "end"),
        calendar=TradingCalendar.XNYS,
    )


def _instrument_ref(config: DataConfig, symbol: SymbolSpec) -> InstrumentRef:
    if symbol.is_future:
        return _futures_ref(config, symbol)
    return _listed_ref(symbol)


def _listed_ref(symbol: SymbolSpec) -> ListedRef:
    if symbol.figi is None:
        raise ValueError(f"store source requires figi for symbol {symbol.symbol_name!r}")
    return ListedRef(symbol.figi)


def _futures_ref(
    config: DataConfig, symbol: SymbolSpec, *, adjustment: str | None = None
) -> FuturesRef:
    if config.dataset is None:
        raise ValueError("data.dataset is required for store futures")
    if symbol.root is None:
        raise ValueError("root is required for store futures")
    return FuturesRef(
        root=symbol.root,
        dataset=config.dataset,
        roll_rule=symbol.roll_rule,
        adjustment=adjustment if adjustment is not None else symbol.adjustment,
    )


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
