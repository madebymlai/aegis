"""Aegis Historical Store Read adapter for RD market data."""

from __future__ import annotations

import pandas as pd
from aegis_data.calendars import TradingCalendar
from aegis_data.coverage import GapFillProvider, ensure_native_bar_coverage
from aegis_data.store import CoveredWindow, HistoricalStore, NativeBarsRequest
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
    signal_refs = tuple(_instrument_ref(symbol) for symbol in config.symbols)
    pnl_refs = tuple(
        _pnl_ref(symbol, signal)
        for symbol, signal in zip(config.symbols, signal_refs, strict=True)
    )
    all_refs = signal_refs + tuple(ref for ref in pnl_refs if ref not in signal_refs)
    request = _native_bars_request(config, all_refs)
    provider = store_gap_fill_provider(config.provider)
    ensure_native_bar_coverage(
        request,
        provider=GapFillProvider(provider),
        locators=_provider_locators(config, signal_refs, pnl_refs),
    )
    frames = _read_native_frames(request, store=HistoricalStore())
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


def _pnl_ref(symbol: SymbolSpec, signal_ref: InstrumentRef) -> InstrumentRef:
    """The P&L-series ref for a dual-adjustment future, else the signal ref itself.

    A future with ``pnl_adjustment`` resolves to a second ``FuturesRef`` differing only
    in adjustment (a distinct store key derived from the same raw legs); every other
    symbol reuses its signal ref, so the P&L panel spans the whole universe.
    """
    if symbol.is_future and symbol.pnl_adjustment is not None:
        return _futures_ref(symbol, adjustment=symbol.pnl_adjustment)
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
    # The request-level calendar governs only venue-agnostic refs: RD's listed
    # universe is US-listed (yfinance) on XNYS.  Futures refs ignore it — the store
    # resolves each contract's expected-bar calendar from its dataset's venue
    # (GLBX -> CME, ICE -> IFUS/IFEU), so a mixed universe needs no per-ref calendar.
    return NativeBarsRequest(
        refs=refs,
        arrays=config.effective_arrays,
        timeframe=config.timeframe,
        start=required_store_window_edge(config.start, "start"),
        end=required_store_window_edge(config.end, "end"),
        calendar=TradingCalendar.XNYS,
    )


def _read_native_frames(
    request: NativeBarsRequest,
    *,
    store: HistoricalStore,
) -> dict[InstrumentRef, pd.DataFrame]:
    window = CoveredWindow(
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        arrays=request.arrays,
        calendar=request.calendar,
        listed_adjustment=request.listed_adjustment,
    )
    return {ref: store.read(ref, window) for ref in request.refs}


def _instrument_ref(symbol: SymbolSpec) -> InstrumentRef:
    if symbol.is_future:
        return _futures_ref(symbol)
    return _listed_ref(symbol)


def _listed_ref(symbol: SymbolSpec) -> ListedRef:
    if symbol.figi is None:
        raise ValueError(f"store source requires figi for symbol {symbol.symbol_name!r}")
    return ListedRef(symbol.figi)


def _futures_ref(symbol: SymbolSpec, *, adjustment: str | None = None) -> FuturesRef:
    if symbol.dataset is None:
        raise ValueError(f"dataset is required for store futures symbol {symbol.root!r}")
    if symbol.root is None:
        raise ValueError("root is required for store futures")
    return FuturesRef(
        root=symbol.root,
        dataset=symbol.dataset,
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
    return reconcile_panels(panels)


def reconcile_panels(panels: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Reconcile a cross-root array panel into a gap-free wide frame (aegis-rd-z5l).

    ``_array_panels`` unions each root's OWN trading days (``pd.DataFrame({symbol: series})``),
    so a day one root trades but another is closed — cross-venue/cross-product holiday-calendar
    divergence (CBOT ags and ICE softs close while Globex runs a holiday session) or a thin
    contract's genuine no-trade day — lands as a NaN cell.  A closed market is not a hole in the
    price process, so the panel is not gated on the least-liquid root; instead it is reconciled,
    parity-consistent with the live path (which simply sees no new bar on a closed day and carries
    the last value):

    - **Interior gaps** (a NaN after a root's first bar) are forward-filled as a flat no-trade
      bar: the root's last settle (``Close``) is carried into every price array, so the day prints
      a doji at the prior close — 0 return, no fabricated intraday range — with ``Volume`` 0.
      (Plain per-array ffill would instead repeat the prior bar's High/Low, inventing volatility
      on a day nothing traded.)
    - **Leading NaN** (a root whose first bar is later than another's) has no prior settle to carry
      back, and back-filling would invent a price that never existed.  The panel is trimmed to the
      common warm-up: the latest first-traded day across roots — the minimal start at which every
      root has a real bar.

    Single-root or already-aligned panels carry no NaN, so reconciliation is a no-op for them.
    """
    if not panels:
        return panels
    common_start = _common_warmup_start(panels)
    if common_start is None:  # nothing listed in any root — leave it for the quality gate to flag
        return panels
    trimmed = {name: panel.loc[common_start:] for name, panel in panels.items()}
    settle = trimmed["Close"].ffill()  # each root's last settle, carried over its closed days
    return {
        name: panel.fillna(0.0)  # a closed day traded nothing
        if name == "Volume"
        else panel.where(panel.notna(), settle)  # flat bar at the carried settle
        for name, panel in trimmed.items()
    }


def _common_warmup_start(panels: dict[str, pd.DataFrame]) -> pd.Timestamp | None:
    """The latest day a root first trades across the panel — the minimal start at which every
    root has a real bar.  A root with no bar at all (all-NaN column) has no first-traded day and
    is skipped, so one fully-missing root does not suppress the warm-up for the rest."""
    starts = [
        first
        for panel in panels.values()
        for column in panel.columns
        if (first := panel[column].first_valid_index()) is not None
    ]
    return max(starts) if starts else None


__all__ = ["load_store_source", "reconcile_panels"]
