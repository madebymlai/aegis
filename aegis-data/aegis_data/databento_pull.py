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
from aegis_data.store import (
    CoverageGap,
    NativeBarsRequest,
    RawFuturesLeg,
    assert_admissible_native_bars,
    covered_row_count,
    merge_raw_futures_leg,
    native_bar_coverage_gaps,
    native_bars_path,
    raw_futures_leg_path,
    read_raw_futures_leg,
    replace_native_bars,
)

# Continuous-futures adjustment vocabulary, named to match NautilusTrader's backward
# ContinuousFutureAdjustmentType modes so research and live agree by construction:
# ``backward_ratio`` (multiplicative, returns-preserving) and ``backward_spread``
# (additive/Panama, point-move & $-P&L preserving).  These map to the generic transform
# primitives (ratio/difference); the "backward" anchor is implicit (newest unadjusted).
_RATIO_ADJUSTMENTS = frozenset({"backward_ratio"})
_CLOSE_DEPENDENT_ADJUSTMENTS = _RATIO_ADJUSTMENTS | {"backward_spread"}
_SUPPORTED_ADJUSTMENTS_MESSAGE = "backward_ratio, backward_spread, or unadjusted"

# Liquidity-leadership eligibility is judged on daily volume regardless of the request
# cadence (ADR-0001): a daily request shares the probe's cache key with its deliverable
# legs (fetched once), while an intraday request keeps the daily probe on its own key.
_DAILY_PROBE_TIMEFRAME = "1D"


@dataclass(frozen=True)
class DatabentoPullResult:
    """Continuous Futures History admitted by a Databento Pull."""

    ref: FuturesRef
    path: Path
    bars: int
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
    raw_legs: tuple[RawFuturesLeg, ...] = ()
    if _continuous_gaps(ref, request, store_dir=store_dir):
        panel, raw_legs = _derive_continuous_history(
            ref,
            request,
            fetch=raw_fetch,
            list_contracts=list_contracts,
            store_dir=store_dir,
            bar_cadence=_request_bar_cadence(request),
        )
        assert_admissible_native_bars(
            ref,
            panel,
            arrays=request.arrays,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            calendar=request.calendar,
        )
        replace_native_bars(
            ref,
            request.timeframe,
            panel,
            required_arrays=request.arrays,
            store_dir=store_dir,
        )
    path = native_bars_path(ref, request.timeframe, store_dir=store_dir)
    return DatabentoPullResult(ref=ref, path=path, bars=covered_row_count(path), raw_legs=raw_legs)


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
    probe_timeframe = _daily_probe_timeframe(request)
    raw_legs: list[RawFuturesLeg] = []

    def raw_leg_fetch(symbol: str, leg_start: date, leg_end: date) -> pd.DataFrame:
        leg = RawFuturesLeg(ref.dataset, symbol)
        raw_legs.append(leg)
        _materialize_raw_leg(
            leg,
            request.timeframe,
            arrays=raw_arrays,
            start=leg_start,
            end=leg_end,
            fetch=fetch,
            store_dir=store_dir,
        )
        return read_raw_futures_leg(
            leg,
            arrays=raw_arrays,
            timeframe=request.timeframe,
            start=leg_start,
            end=_exclusive_date_end(leg_end),
            store_dir=store_dir,
        )

    def probe_daily_volume(symbol: str, probe_start: date, probe_end: date) -> pd.Series:
        # Rank a candidate on daily volume.  The 1d candidate leg is retained as Raw
        # Futures Leg source material (presence-cached) but is *not* appended to
        # ``raw_legs``, so a serial probed here stays cached-but-unused — excluded from
        # the continuous derivation.  ``fetch`` is the daily port today (BarAggregation.
        # DAY); an intraday deliverable fetcher would build a daily probe fetcher here.
        leg = RawFuturesLeg(ref.dataset, symbol)
        _materialize_raw_leg(
            leg,
            probe_timeframe,
            arrays=raw_arrays,
            start=probe_start,
            end=probe_end,
            fetch=fetch,
            store_dir=store_dir,
        )
        volume = read_raw_futures_leg(
            leg,
            arrays=("Volume",),
            timeframe=probe_timeframe,
            start=probe_start,
            end=_exclusive_date_end(probe_end),
            store_dir=store_dir,
        )
        return volume["Volume"]

    chain = fetch_contract_chain(
        ref.root,
        start,
        end,
        list_contracts=list_contracts,
        fetch=raw_leg_fetch,
        bar_cadence=bar_cadence,
        probe_volume=probe_daily_volume,
    )
    return _continuous_panel(chain, adjustment=ref.adjustment), tuple(dict.fromkeys(raw_legs))


def _request_bar_cadence(request: NativeBarsRequest) -> timedelta:
    """The request's bar cadence as a duration; the roll lead derives from it."""
    return pd.Timedelta(request.timeframe).to_pytimedelta()


def _daily_probe_timeframe(request: NativeBarsRequest) -> str:
    """The timeframe of the daily liquidity-ranking probe (ADR-0001).

    A daily request reuses its own timeframe so the probe and the deliverable legs are
    one cached fetch; any coarser/intraday request keeps the probe on the canonical
    daily key, so eligibility never depends on the sampling cadence.
    """
    if _request_bar_cadence(request) == timedelta(days=1):
        return request.timeframe
    return _DAILY_PROBE_TIMEFRAME


def _materialize_raw_leg(
    leg: RawFuturesLeg,
    timeframe: str,
    *,
    arrays: tuple[str, ...],
    start: date,
    end: date,
    fetch: ContractFetcher,
    store_dir: Path | None,
) -> None:
    """Fetch a dated contract's bars once and retain them as source material.

    A leg is provider source material, not a covered deliverable: we fetch the whole
    window the first time and cache it; the contract's actual traded days are whatever
    the provider returns (a thin/serial contract prints sparsely and stops at its last
    trade).  Coverage is enforced on the assembled continuous series, never per leg.
    """
    if raw_futures_leg_path(leg.dataset, leg.symbol, timeframe, store_dir=store_dir).exists():
        return
    merge_raw_futures_leg(
        leg, timeframe, fetch(leg.symbol, start, end), required_arrays=arrays, store_dir=store_dir
    )


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
    request: NativeBarsRequest,
    *,
    store_dir: Path | None,
) -> tuple[CoverageGap, ...]:
    return native_bar_coverage_gaps(
        ref,
        arrays=request.arrays,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        calendar=request.calendar,
        store_dir=store_dir,
    )


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


def _exclusive_date_end(value: date) -> pd.Timestamp:
    return pd.Timestamp(value) + pd.Timedelta(days=1)


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
