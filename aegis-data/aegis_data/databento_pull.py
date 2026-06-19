"""Databento futures Pull orchestration through Nautilus raw-leg source material."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from aegis_runtime import FuturesRef

from aegis_data.back_adjust import back_adjust_chain
from aegis_data.chain import ContractCalendar, ContractChain, ContractFetcher, fetch_contract_chain
from aegis_data.continuous import apply_adjustment_factors
from aegis_data.databento_port import databento_contract_calendar, databento_port_fetcher
from aegis_data.roll import DEFAULT_ROLL_LEAD_DAYS
from aegis_data.store import (
    CoverageGap,
    NativeBarsRequest,
    RawFuturesLeg,
    assert_admissible_native_bars,
    covered_row_count,
    merge_raw_futures_leg,
    native_bar_coverage_gaps,
    native_bars_path,
    raw_futures_leg_coverage_gaps,
    read_raw_futures_leg,
    replace_native_bars,
)

_RATIO_ADJUSTMENTS = frozenset({"back_adjust", "ratio"})
_CLOSE_DEPENDENT_ADJUSTMENTS = _RATIO_ADJUSTMENTS | {"difference"}
_SUPPORTED_ADJUSTMENTS_MESSAGE = "back_adjust, ratio, difference, or unadjusted"


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
    roll_lead_days: int = DEFAULT_ROLL_LEAD_DAYS,
) -> DatabentoPullResult:
    """Pull one ``FuturesRef`` and materialize Continuous Futures History.

    Raw dated-contract legs are retained as provider source material under the
    dataset+symbol key.  Continuous history is a derived Covered History keyed by
    the requested ``FuturesRef`` (root, dataset, roll rule, adjustment).
    """
    ref = _single_futures_ref(request)
    _require_supported_roll_rule(ref)
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
            roll_lead_days=roll_lead_days,
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
    roll_lead_days: int,
) -> tuple[pd.DataFrame, tuple[RawFuturesLeg, ...]]:
    start, end = _request_dates(request)
    raw_arrays = _raw_required_arrays(ref, request)
    raw_legs: list[RawFuturesLeg] = []

    def raw_leg_fetch(symbol: str, leg_start: date, leg_end: date) -> pd.DataFrame:
        leg = RawFuturesLeg(ref.dataset, symbol)
        raw_legs.append(leg)
        _fill_raw_leg_gaps(
            leg,
            request,
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
            calendar=request.calendar,
            store_dir=store_dir,
        )

    chain = fetch_contract_chain(
        ref.root,
        start,
        end,
        list_contracts=list_contracts,
        fetch=raw_leg_fetch,
        roll_lead_days=roll_lead_days,
    )
    return _continuous_panel(chain, adjustment=ref.adjustment), tuple(dict.fromkeys(raw_legs))


def _fill_raw_leg_gaps(
    leg: RawFuturesLeg,
    request: NativeBarsRequest,
    *,
    arrays: tuple[str, ...],
    start: date,
    end: date,
    fetch: ContractFetcher,
    store_dir: Path | None,
) -> None:
    for gap in _raw_leg_gaps(leg, request, arrays=arrays, start=start, end=end, store_dir=store_dir):
        bars = fetch(leg.symbol, gap.start.date(), _inclusive_gap_end(gap))
        assert_admissible_native_bars(
            leg,
            bars,
            arrays=arrays,
            timeframe=request.timeframe,
            start=gap.start,
            end=gap.end,
            calendar=request.calendar,
        )
        merge_raw_futures_leg(
            leg,
            request.timeframe,
            bars,
            required_arrays=arrays,
            store_dir=store_dir,
        )


def _continuous_panel(chain: ContractChain, *, adjustment: str) -> pd.DataFrame:
    if adjustment in _RATIO_ADJUSTMENTS:
        return back_adjust_chain(chain, method="ratio")
    if adjustment == "difference":
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


def _raw_leg_gaps(
    leg: RawFuturesLeg,
    request: NativeBarsRequest,
    *,
    arrays: tuple[str, ...],
    start: date,
    end: date,
    store_dir: Path | None,
) -> tuple[CoverageGap, ...]:
    return raw_futures_leg_coverage_gaps(
        leg,
        arrays=arrays,
        timeframe=request.timeframe,
        start=start,
        end=_exclusive_date_end(end),
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


def _inclusive_gap_end(gap: CoverageGap) -> date:
    return (gap.end - pd.Timedelta(days=1)).date()


def _exclusive_date_end(value: date) -> pd.Timestamp:
    return pd.Timestamp(value) + pd.Timedelta(days=1)


def _single_futures_ref(request: NativeBarsRequest) -> FuturesRef:
    if len(request.refs) != 1:
        raise ValueError("Databento futures Pull requires exactly one InstrumentRef")
    ref = request.refs[0]
    if not isinstance(ref, FuturesRef):
        raise TypeError(f"Databento futures Pull requires a FuturesRef; got {ref!r}")
    return ref


def _require_supported_roll_rule(ref: FuturesRef) -> None:
    if ref.roll_rule != "calendar":
        raise ValueError(f"unsupported futures roll rule {ref.roll_rule!r}; expected calendar")


__all__ = ["DatabentoPullResult", "pull_databento_futures_bars"]
