"""Databento futures Pull orchestration through Nautilus raw-leg source material."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from aegis_runtime import FuturesRef

from aegis_data.back_adjust import back_adjust_chain
from aegis_data.calendars import venue_calendar_for_dataset
from aegis_data.chain import ContractCalendar, ContractChain, ContractFetcher, fetch_contract_chain
from aegis_data.continuous import apply_adjustment_factors
from aegis_data.databento_port import databento_contract_calendar, databento_port_fetcher
from aegis_data.raw_leg_cache import raw_leg_ports
from aegis_data.store import (
    CoveredWindow,
    CoverageGap,
    HistoricalStore,
    NativeBarsRequest,
    RawFuturesLeg,
    WriteMode,
)

# Continuous-futures adjustment vocabulary, named to match NautilusTrader's backward
# ContinuousFutureAdjustmentType modes so research and live agree by construction:
# ``backward_ratio`` (multiplicative, returns-preserving) and ``backward_spread``
# (additive/Panama, point-move & $-P&L preserving).  These map to the generic transform
# primitives (ratio/difference); the "backward" anchor is implicit (newest unadjusted).
_RATIO_ADJUSTMENTS = frozenset({"backward_ratio"})
_CLOSE_DEPENDENT_ADJUSTMENTS = _RATIO_ADJUSTMENTS | {"backward_spread"}
_SUPPORTED_ADJUSTMENTS_MESSAGE = "backward_ratio, backward_spread, or unadjusted"


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
    raw_arrays = _raw_required_arrays(ref, request)
    ports = raw_leg_ports(
        dataset=ref.dataset,
        timeframe=request.timeframe,
        fetch=fetch,
        arrays=raw_arrays,
        store_dir=store_dir,
    )
    raw_legs: list[RawFuturesLeg] = []

    def raw_leg_fetch(symbol: str, leg_start: date, leg_end: date) -> pd.DataFrame:
        leg = RawFuturesLeg(ref.dataset, symbol)
        raw_legs.append(leg)
        return ports.fetch(symbol, leg_start, leg_end)

    chain = fetch_contract_chain(
        ref.root,
        start,
        end,
        list_contracts=list_contracts,
        fetch=raw_leg_fetch,
        bar_cadence=bar_cadence,
        probe_volume=ports.probe,
    )
    return _continuous_panel(chain, adjustment=ref.adjustment), tuple(dict.fromkeys(raw_legs))


def _request_bar_cadence(request: NativeBarsRequest) -> timedelta:
    """The request's bar cadence as a duration; the roll lead derives from it."""
    return pd.Timedelta(request.timeframe).to_pytimedelta()


def _continuous_panel(chain: ContractChain, *, adjustment: str) -> pd.DataFrame:
    if adjustment in _RATIO_ADJUSTMENTS:
        return back_adjust_chain(chain, method="ratio")
    if adjustment == "backward_spread":
        return back_adjust_chain(chain, method="difference")
    if adjustment == "unadjusted":
        return _unadjusted_chain(chain)
    raise ValueError(
        f"unsupported futures adjustment {adjustment!r}; expected {_SUPPORTED_ADJUSTMENTS_MESSAGE}"
    )


def _unadjusted_chain(chain: ContractChain) -> pd.DataFrame:
    identity = tuple(1.0 for _ in chain.frames)
    columns: dict[str, pd.Series] = {}
    for column in chain.frames[0].columns:
        series = [frame[column] for frame in chain.frames]
        columns[column] = apply_adjustment_factors(
            series,
            chain.roll_dates,
            identity,
            method="ratio",
        )
    return pd.DataFrame(columns)


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
