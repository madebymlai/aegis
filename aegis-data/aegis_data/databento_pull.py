"""Databento futures Pull orchestration through Nautilus raw-leg source material."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from aegis_runtime import FuturesRef

from aegis_data.calendars import venue_calendar_for_dataset
from aegis_data.chain import ContractCalendar, ContractFetcher
from aegis_data.databento_port import databento_contract_calendar, databento_port_fetcher
from aegis_data.raw_leg_cache import LegPorts, raw_leg_ports
from aegis_data.source import continuous_panel
from aegis_data.store import (
    CoveredWindow,
    CoverageGap,
    HistoricalStore,
    NativeBarsRequest,
    RawFuturesLeg,
    WriteMode,
)

# Continuous-futures adjustment vocabulary → generic back-adjust transform method, the
# single authority for which adjustments a Pull supports.  Names match NautilusTrader's
# backward ContinuousFutureAdjustmentType modes so research and live agree by construction:
# ``backward_ratio`` (multiplicative, returns-preserving) and ``backward_spread``
# (additive/Panama, point-move & $-P&L preserving) map to the generic ratio/difference
# primitives; ``unadjusted`` stitches the raw series with no factor (``none``).  The
# "backward" anchor is implicit (newest contract unadjusted).
_ADJUSTMENT_METHODS = {
    "backward_ratio": "ratio",
    "backward_spread": "difference",
    "unadjusted": "none",
}
# Adjustments whose roll factor is derived from Close (every method but the raw stitch):
# these need the Close array even when the caller did not request it.
_CLOSE_DEPENDENT_ADJUSTMENTS = frozenset(
    adjustment for adjustment, method in _ADJUSTMENT_METHODS.items() if method != "none"
)
_SUPPORTED_ADJUSTMENTS_MESSAGE = ", ".join(_ADJUSTMENT_METHODS)


@dataclass(frozen=True)
class DatabentoPullResult:
    """Continuous Futures History admitted by a Databento Pull."""

    ref: FuturesRef
    raw_legs: tuple[RawFuturesLeg, ...]


def pull_databento_futures_bars(
    request: NativeBarsRequest,
    *,
    fetcher: ContractFetcher | None = None,
    contract_calendar: ContractCalendar | None = None,
    client=None,
    store_dir: Path | None = None,
) -> DatabentoPullResult:
    """Pull one ``FuturesRef`` and materialize Continuous Futures History.

    Raw dated-contract legs are retained as provider source material under the
    dataset+symbol key.  Continuous history is a derived Covered History keyed by
    the requested ``FuturesRef`` (root, dataset, roll rule, adjustment).  The roll
    lead is derived from the request's bar cadence — never configured.
    """
    ref = _single_futures_ref(request)
    _require_supported_roll_rule(ref)
    request = _with_venue_calendar(request, ref)
    raw_fetch = fetcher or databento_port_fetcher(ref.dataset, client=client)
    list_contracts = contract_calendar or databento_contract_calendar(ref.dataset, client=client)
    store = _store(store_dir)
    window = _covered_window(request)
    raw_legs: tuple[RawFuturesLeg, ...] = ()
    if _continuous_gaps(ref, window, store=store):
        panel, raw_legs = _derive_continuous_history(
            ref,
            request,
            fetch=raw_fetch,
            list_contracts=list_contracts,
            store_dir=store_dir,
            bar_cadence=_request_bar_cadence(request),
        )
        store.assert_admissible(ref, panel, window)
        store.write(ref, panel, window, mode=WriteMode.REPLACE)
    return DatabentoPullResult(ref=ref, raw_legs=raw_legs)


def _derive_continuous_history(
    ref: FuturesRef,
    request: NativeBarsRequest,
    *,
    fetch: ContractFetcher,
    list_contracts: ContractCalendar,
    store_dir: Path | None,
    bar_cadence: timedelta,
) -> tuple[pd.DataFrame, tuple[RawFuturesLeg, ...]]:
    start, end = _request_dates(request)
    ports = raw_leg_ports(
        dataset=ref.dataset,
        timeframe=request.timeframe,
        fetch=fetch,
        arrays=_raw_required_arrays(ref, request),
        store_dir=store_dir,
    )
    raw_legs: list[RawFuturesLeg] = []

    def record_leg(symbol: str, leg_start: date, leg_end: date) -> pd.DataFrame:
        raw_legs.append(RawFuturesLeg(ref.dataset, symbol))
        return ports.fetch(symbol, leg_start, leg_end)

    panel = continuous_panel(
        ref.root,
        start,
        end,
        ports=LegPorts(fetch=record_leg, probe=ports.probe),
        list_contracts=list_contracts,
        method=_adjustment_method(ref.adjustment),
        bar_cadence=bar_cadence,
    )
    return panel, tuple(dict.fromkeys(raw_legs))


def _request_bar_cadence(request: NativeBarsRequest) -> timedelta:
    """The request's bar cadence as a duration; the roll lead derives from it."""
    return pd.Timedelta(request.timeframe).to_pytimedelta()


def _adjustment_method(adjustment: str) -> str:
    """The generic back-adjust transform method for a FuturesRef adjustment."""
    try:
        return _ADJUSTMENT_METHODS[adjustment]
    except KeyError:
        raise ValueError(
            f"unsupported futures adjustment {adjustment!r}; expected {_SUPPORTED_ADJUSTMENTS_MESSAGE}"
        ) from None


def _continuous_gaps(
    ref: FuturesRef,
    window: CoveredWindow,
    *,
    store: HistoricalStore,
) -> tuple[CoverageGap, ...]:
    return store.coverage_gaps(ref, window)


def _covered_window(request: NativeBarsRequest) -> CoveredWindow:
    return CoveredWindow(
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        arrays=request.arrays,
        calendar=request.calendar,
        listed_adjustment=request.listed_adjustment,
    )


def _store(store_dir: Path | None) -> HistoricalStore:
    return HistoricalStore(store_dir) if store_dir is not None else HistoricalStore()


def _raw_required_arrays(ref: FuturesRef, request: NativeBarsRequest) -> tuple[str, ...]:
    arrays = list(request.arrays)
    if ref.adjustment in _CLOSE_DEPENDENT_ADJUSTMENTS and not _has_array(arrays, "Close"):
        arrays.append("Close")
    return tuple(arrays)


def _has_array(arrays: list[str], name: str) -> bool:
    normalized = name.lower()
    return any(array.lower() == normalized for array in arrays)


def _request_dates(request: NativeBarsRequest) -> tuple[date, date]:
    start = pd.Timestamp(request.start).date()
    end_exclusive = pd.Timestamp(request.end)
    return start, (end_exclusive - pd.Timedelta(days=1)).date()


def _single_futures_ref(request: NativeBarsRequest) -> FuturesRef:
    if len(request.refs) != 1:
        raise ValueError("Databento futures Pull requires exactly one InstrumentRef")
    ref = request.refs[0]
    if not isinstance(ref, FuturesRef):
        raise TypeError(f"Databento futures Pull requires a FuturesRef; got {ref!r}")
    return ref


def _with_venue_calendar(request: NativeBarsRequest, ref: FuturesRef) -> NativeBarsRequest:
    """Re-key the request to the contract's venue calendar, resolved from its dataset.

    A futures Pull's expected-bar grid is the venue's (CME/ICE) — known from the
    ref's dataset — not the request-level calendar (which governs venue-agnostic
    refs).  Every leg admission and the continuous series then cover against it, so
    a day NYSE is open but the venue closed (or vice versa) is no longer a false gap.
    """
    return replace(request, calendar=venue_calendar_for_dataset(ref.dataset))


def _require_supported_roll_rule(ref: FuturesRef) -> None:
    if ref.roll_rule != "calendar":
        raise ValueError(f"unsupported futures roll rule {ref.roll_rule!r}; expected calendar")


__all__ = ["DatabentoPullResult", "pull_databento_futures_bars"]
