"""OS-global parquet store for historical market data.

Provider-normalized history is stored as a reusable corpus under the OS
user-data directory (``platformdirs``), overridable with ``AEGIS_DATA_DIR``.
Store Reads are coverage-based, and Pulls can fill only instrument-calendar Gaps
instead of re-fetching already covered intervals.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias, TypeVar

import pandas as pd
import platformdirs
from aegis_runtime import FuturesRef, InstrumentRef, ListedRef

from aegis_data.calendars import (
    TradingCalendar,
    as_trading_calendar,
    venue_calendar_for_dataset,
)
from aegis_data.store_coverage import (
    CoverageGap,
    HistoryWindow,
    StoreCoverage,
    StoreCoverageError,
    history_column_lookup,
    missing_history_columns,
    select_history_columns,
)

_APP = "aegis-data"
NATIVE_OHLCV_ARRAYS = ("Open", "High", "Low", "Close", "Volume")
_HistoryFrame = TypeVar("_HistoryFrame", pd.Series, pd.DataFrame)


class ListedAdjustmentPolicy(StrEnum):
    """Listed native-bar adjustment policy in the Historical Store identity."""

    RAW = "raw"


@dataclass(frozen=True, order=True)
class FxPair:
    """FX History identity: quote units per one base currency unit."""

    base: str
    quote: str

    def __post_init__(self) -> None:
        for name, value in (("base", self.base), ("quote", self.quote)):
            if not isinstance(value, str) or not value:
                raise ValueError(f"FxPair {name} must be a non-empty string; got {value!r}")
            normalized = value.upper()
            object.__setattr__(self, name, normalized)
        if self.base == self.quote:
            raise ValueError(f"FxPair currencies must differ; got {self.base}/{self.quote}")

    @property
    def value(self) -> str:
        """Stable string payload used where a human-readable label is needed."""
        return f"{self.base}/{self.quote}"


@dataclass(frozen=True, order=True)
class RawFuturesLeg:
    """Provider source material for one dated futures contract."""

    dataset: str
    symbol: str

    def __post_init__(self) -> None:
        for name, value in (("dataset", self.dataset), ("symbol", self.symbol)):
            if not isinstance(value, str) or not value:
                raise ValueError(f"RawFuturesLeg {name} must be a non-empty string; got {value!r}")

    @property
    def value(self) -> str:
        """Stable string payload used where a human-readable label is needed."""
        return f"{self.dataset}:{self.symbol}"

    @property
    def tolerates_interior_missing_bars(self) -> bool:
        """Raw contract source material may be legitimately sparse inside its life."""
        return True

HistoryKey: TypeAlias = InstrumentRef | FxPair | RawFuturesLeg


class StoreAdmissionError(ValueError):
    """Historical data cannot be admitted as Covered History."""


@dataclass(frozen=True)
class NativeBarsRequest:
    """Neutral Covered History request for native market bars."""

    refs: Sequence[InstrumentRef]
    arrays: Sequence[str]
    timeframe: str
    start: str | date | pd.Timestamp
    end: str | date | pd.Timestamp
    calendar: TradingCalendar | str
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW

    def __post_init__(self) -> None:
        refs = tuple(self.refs)
        if not refs:
            raise ValueError("NativeBarsRequest requires at least one InstrumentRef")
        object.__setattr__(self, "refs", refs)
        object.__setattr__(self, "arrays", _validated_arrays(self.arrays))
        if not self.timeframe:
            raise ValueError("NativeBarsRequest timeframe must be a non-empty string")
        object.__setattr__(self, "calendar", as_trading_calendar(self.calendar))
        object.__setattr__(
            self,
            "listed_adjustment",
            _listed_adjustment_policy(self.listed_adjustment),
        )
        HistoryWindow(
            timeframe=self.timeframe,
            calendar=self.calendar,
            start=self.start,
            end=self.end,
        )


def data_dir() -> Path:
    """The historical-data store root: ``$AEGIS_DATA_DIR`` or the OS user-data dir."""
    override = os.environ.get("AEGIS_DATA_DIR")
    return Path(override) if override else Path(platformdirs.user_data_dir(_APP))


def fx_history_path(
    pair: FxPair,
    timeframe: str,
    *,
    store_dir: Path | None = None,
) -> Path:
    """Parquet location for an FX History Covered History slice."""
    return (
        _store_root(store_dir)
        / "fx"
        / _safe_key(pair.base)
        / _safe_key(pair.quote)
        / f"{_safe_key(timeframe)}.parquet"
    )


def raw_futures_leg_path(
    dataset: str,
    symbol: str,
    timeframe: str,
    *,
    store_dir: Path | None = None,
) -> Path:
    """Parquet location for a Raw Futures Leg source-material slice."""
    return (
        raw_futures_dir(dataset, store_dir=store_dir)
        / _safe_key(symbol)
        / f"{_safe_key(timeframe)}.parquet"
    )


def raw_futures_dir(dataset: str, *, store_dir: Path | None = None) -> Path:
    return _store_root(store_dir) / "futures-raw" / _safe_key(dataset)


def _raw_futures_leg_coverage_path(
    leg: RawFuturesLeg,
    timeframe: str,
    *,
    store_dir: Path | None = None,
) -> Path:
    return (
        raw_futures_dir(leg.dataset, store_dir=store_dir)
        / _safe_key(leg.symbol)
        / ".coverage"
        / f"{_safe_key(timeframe)}.parquet"
    )


def native_bars_path(
    ref: InstrumentRef,
    timeframe: str,
    *,
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW,
    store_dir: Path | None = None,
) -> Path:
    """Parquet location for a native-market-bar Covered History slice.

    Listed instruments are keyed by ``ListedRef`` (FIGI), and futures are keyed
    by their continuous ``FuturesRef`` contract, never by provider ticker.  The
    path is intentionally exposed so tests can fixture-seed the Historical Store
    without introducing a provider.
    """
    root = _store_root(store_dir)
    if isinstance(ref, ListedRef):
        adjustment = _listed_adjustment_policy(listed_adjustment)
        return (
            root
            / "listed"
            / _safe_key(ref.figi)
            / "bars"
            / _safe_key(adjustment.value)
            / f"{_safe_key(timeframe)}.parquet"
        )
    if isinstance(ref, FuturesRef):
        return (
            root
            / "futures-ref"
            / _safe_key(ref.dataset)
            / _safe_key(ref.root)
            / _safe_key(ref.roll_rule)
            / f"{_safe_key(ref.adjustment)}_{_safe_key(timeframe)}.parquet"
        )
    raise TypeError(f"unsupported InstrumentRef {ref!r}")


def write_native_bars(
    ref: InstrumentRef,
    timeframe: str,
    bars: pd.DataFrame,
    *,
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW,
    required_arrays: Sequence[str] = (),
    store_dir: Path | None = None,
) -> Path:
    """Admit provider-normalized native market bars as Covered History.

    The frame is stored as-is apart from deterministic index sorting. Prices stay
    in the instrument's native quote currency; Store Read returns pandas frames,
    never Nautilus engine objects.
    """
    admitted = _admit_native_bars(bars)
    _assert_admitted_native_bar_arrays(admitted, required_arrays)
    path = native_bars_path(
        ref,
        timeframe,
        listed_adjustment=listed_adjustment,
        store_dir=store_dir,
    )
    return _write_admitted_native_bars(path, admitted)


def merge_native_bars(
    ref: InstrumentRef,
    timeframe: str,
    bars: pd.DataFrame,
    *,
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW,
    required_arrays: Sequence[str] = (),
    store_dir: Path | None = None,
) -> Path:
    """Add provider-normalized native market bars to existing Covered History.

    Additive and idempotent: on an overlapping timestamp the already-admitted
    Covered History wins, so a re-Pull never silently rewrites admitted bars. Use
    :func:`replace_native_bars` to overwrite an existing window (e.g. to repair a
    bad bar or re-derive a continuous panel).
    """
    admitted = _admit_native_bars(bars)
    _assert_admitted_native_bar_arrays(admitted, required_arrays)
    path = native_bars_path(
        ref,
        timeframe,
        listed_adjustment=listed_adjustment,
        store_dir=store_dir,
    )
    merged = _merge_admitted_native_bars(path, admitted) if path.exists() else admitted
    return _write_admitted_native_bars(path, merged)


def replace_native_bars(
    ref: InstrumentRef,
    timeframe: str,
    bars: pd.DataFrame,
    *,
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW,
    required_arrays: Sequence[str] = (),
    store_dir: Path | None = None,
) -> Path:
    """Replace an overlapping Covered History window with provider-normalized bars.

    The new bars win across their own ``[min, max]`` span (so a re-derived
    continuous panel can change historical values); admitted bars outside that
    span are retained. Unlike :func:`merge_native_bars`, this overwrites overlap.
    """
    admitted = _admit_native_bars(bars)
    _assert_admitted_native_bar_arrays(admitted, required_arrays)
    path = native_bars_path(
        ref,
        timeframe,
        listed_adjustment=listed_adjustment,
        store_dir=store_dir,
    )
    merged = _replace_admitted_native_bars(path, admitted) if path.exists() else admitted
    return _write_admitted_native_bars(path, merged)


def read_native_bars(
    refs: Sequence[InstrumentRef],
    *,
    arrays: Sequence[str],
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    calendar: TradingCalendar | str,
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW,
    store_dir: Path | None = None,
) -> dict[InstrumentRef, pd.DataFrame]:
    """Provider-free Store Read for native market bars.

    Reads Covered History for each ``InstrumentRef`` and returns one native
    pandas frame per ref, sliced to ``[start, end)``.  Missing files, arrays,
    NaNs, or bars expected by ``calendar`` fail closed before a backtest can run.
    """
    return read_native_bars_request(
        NativeBarsRequest(
            refs=refs,
            arrays=arrays,
            timeframe=timeframe,
            start=start,
            end=end,
            calendar=calendar,
            listed_adjustment=listed_adjustment,
        ),
        store_dir=store_dir,
    )


def read_native_bars_request(
    request: NativeBarsRequest,
    *,
    store_dir: Path | None = None,
) -> dict[InstrumentRef, pd.DataFrame]:
    """Provider-free Store Read for a neutral native-bars request."""
    arrays = tuple(request.arrays)
    listed_adjustment = _listed_adjustment_policy(request.listed_adjustment)
    calendar = as_trading_calendar(request.calendar)
    return {
        ref: _read_one_native_bar_frame(
            ref,
            arrays=arrays,
            timeframe=request.timeframe,
            listed_adjustment=listed_adjustment,
            calendar=calendar,
            start=request.start,
            end=request.end,
            store_dir=store_dir,
        )
        for ref in request.refs
    }


def native_bar_coverage_gaps(
    ref: InstrumentRef,
    *,
    arrays: Sequence[str],
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    calendar: TradingCalendar | str,
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW,
    store_dir: Path | None = None,
) -> tuple[CoverageGap, ...]:
    """Return uncovered expected-bar intervals for a native-bars request."""
    window = HistoryWindow(timeframe=timeframe, calendar=calendar, start=start, end=end)
    required = _validated_arrays(arrays)
    path = native_bars_path(
        ref,
        timeframe,
        listed_adjustment=listed_adjustment,
        store_dir=store_dir,
    )
    observed = _load_admitted_native_bars_or_empty(path, required)
    return StoreCoverage.for_native_bars(ref, arrays=required).gaps(window, observed)


def merge_raw_futures_leg(
    leg: RawFuturesLeg,
    timeframe: str,
    bars: pd.DataFrame,
    *,
    required_arrays: Sequence[str] = (),
    store_dir: Path | None = None,
) -> Path:
    """Add provider-normalized bars to a Raw Futures Leg corpus."""
    admitted = _admit_native_bars(bars)
    _assert_admitted_native_bar_arrays(admitted, required_arrays)
    path = raw_futures_leg_path(leg.dataset, leg.symbol, timeframe, store_dir=store_dir)
    merged = _merge_admitted_native_bars(path, admitted) if path.exists() else admitted
    return _write_admitted_native_bars(path, merged)


def read_raw_futures_leg(
    leg: RawFuturesLeg,
    *,
    arrays: Sequence[str],
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    store_dir: Path | None = None,
) -> pd.DataFrame:
    """Read one Raw Futures Leg source-material slice (no expected-bar grid).

    A dated contract leg is provider source material: the chain places its roll seam
    at the snapped common trading day and the assembled continuous series carries the
    coverage guarantee, so a leg read returns exactly what the contract traded in the
    window — a thin contract that prints sparsely or stops before its expiry is not a
    gap here.
    """
    window = HistoryWindow(
        timeframe=timeframe,
        calendar=TradingCalendar.CONTINUOUS,
        start=start,
        end=end,
    )
    path = raw_futures_leg_path(leg.dataset, leg.symbol, timeframe, store_dir=store_dir)
    if not path.exists():
        raise StoreCoverageError(leg, f"no Raw Futures Leg for {timeframe}")
    return _read_raw_futures_leg_slice(leg, path, arrays=arrays, window=window)


def read_raw_futures_leg_or_empty(
    leg: RawFuturesLeg,
    *,
    arrays: Sequence[str],
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    store_dir: Path | None = None,
) -> pd.DataFrame:
    """Read a Raw Futures Leg source-material slice, or an empty frame on a cold leg."""
    window = HistoryWindow(
        timeframe=timeframe,
        calendar=TradingCalendar.CONTINUOUS,
        start=start,
        end=end,
    )
    path = raw_futures_leg_path(leg.dataset, leg.symbol, timeframe, store_dir=store_dir)
    return _read_raw_futures_leg_slice(
        leg,
        path,
        arrays=arrays,
        window=window,
        missing_ok=True,
    )


def record_raw_futures_leg_coverage(
    leg: RawFuturesLeg,
    timeframe: str,
    *,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    store_dir: Path | None = None,
) -> Path:
    """Remember a fetched half-open Raw Futures Leg window, even when it had no bars."""
    coverage = _admit_raw_futures_leg_coverage(
        pd.DataFrame({"start": [start], "end": [end]})
    )
    path = _raw_futures_leg_coverage_path(leg, timeframe, store_dir=store_dir)
    if path.exists():
        coverage = _coalesce_raw_futures_leg_coverage(
            pd.concat([_load_raw_futures_leg_coverage(path), coverage])
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    coverage.to_parquet(path)
    return path


def read_raw_futures_leg_coverage(
    leg: RawFuturesLeg,
    timeframe: str,
    *,
    store_dir: Path | None = None,
) -> tuple[CoverageGap, ...]:
    """Fetched half-open Raw Futures Leg windows for cache coverage decisions."""
    path = _raw_futures_leg_coverage_path(leg, timeframe, store_dir=store_dir)
    if not path.exists():
        return ()
    coverage = _load_raw_futures_leg_coverage(path)
    return tuple(
        CoverageGap(start=row.start, end=row.end)
        for row in coverage.itertuples(index=False)
    )


def assert_native_bar_coverage(
    key: HistoryKey,
    frame: pd.DataFrame,
    *,
    arrays: Sequence[str],
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    calendar: TradingCalendar | str,
) -> None:
    """Fail when a provider frame cannot cover the requested native-bar window."""
    window = HistoryWindow(timeframe=timeframe, calendar=calendar, start=start, end=end)
    required = _validated_arrays(arrays)
    admitted = _admit_native_bars(frame)
    StoreCoverage.for_native_bars(key, arrays=required).slice(window, admitted)


def write_fx_history(
    pair: FxPair,
    timeframe: str,
    rates: pd.Series,
    *,
    store_dir: Path | None = None,
) -> Path:
    """Admit provider-normalized FX rates as Covered History.

    Rates are quote-currency units per one base-currency unit, stored separately
    from instrument native market bars so conversion inputs can be reused across
    instruments and backtests.
    """
    admitted = _admit_fx_history(rates)
    path = fx_history_path(pair, timeframe, store_dir=store_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    admitted.to_parquet(path)
    return path


def merge_fx_history(
    pair: FxPair,
    timeframe: str,
    rates: pd.Series,
    *,
    store_dir: Path | None = None,
) -> Path:
    """Add provider-normalized FX rates to existing FX History."""
    admitted = _admit_fx_history(rates)
    path = fx_history_path(pair, timeframe, store_dir=store_dir)
    merged = _merge_admitted_fx_history(path, admitted) if path.exists() else admitted
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path)
    return path


def read_fx_history(
    pairs: Sequence[FxPair],
    *,
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    calendar: TradingCalendar | str,
    store_dir: Path | None = None,
) -> dict[FxPair, pd.Series]:
    """Provider-free Store Read for FX History.

    Reads Covered History for each ``FxPair`` and returns one rate series per
    pair, sliced to ``[start, end)``. Missing files, NaNs, or rates expected by
    ``calendar`` fail closed before Trader valuation or conversion can run.
    """
    return {
        pair: _read_one_fx_series(
            pair,
            timeframe=timeframe,
            calendar=calendar,
            start=start,
            end=end,
            store_dir=store_dir,
        )
        for pair in pairs
    }


def fx_history_coverage_gaps(
    pair: FxPair,
    *,
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    calendar: TradingCalendar | str,
    store_dir: Path | None = None,
) -> tuple[CoverageGap, ...]:
    """Return uncovered expected-rate intervals for an FX History request."""
    window = HistoryWindow(timeframe=timeframe, calendar=calendar, start=start, end=end)
    path = fx_history_path(pair, timeframe, store_dir=store_dir)
    observed = _load_admitted_fx_history_or_empty(path)
    return StoreCoverage.for_fx_rates(pair).gaps(window, observed)


def assert_fx_history_coverage(
    pair: FxPair,
    rates: pd.Series,
    *,
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    calendar: TradingCalendar | str,
) -> None:
    """Fail when a provider series cannot cover the requested FX History window."""
    window = HistoryWindow(timeframe=timeframe, calendar=calendar, start=start, end=end)
    admitted = _admit_fx_history(rates)
    StoreCoverage.for_fx_rates(pair).slice(window, admitted)


def covered_row_count(path: Path) -> int:
    """Number of admitted rows in a Covered History slice (0 when absent)."""
    if not path.exists():
        return 0
    return len(pd.read_parquet(path))


def assert_admissible_native_bars(
    key: HistoryKey,
    frame: pd.DataFrame,
    *,
    arrays: Sequence[str],
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    calendar: TradingCalendar | str,
) -> None:
    """Pull admission: reject provider native bars a Store Read could not cover."""
    _as_admission(
        lambda: assert_native_bar_coverage(
            key,
            frame,
            arrays=arrays,
            timeframe=timeframe,
            start=start,
            end=end,
            calendar=calendar,
        )
    )


def assert_admissible_fx_history(
    pair: FxPair,
    rates: pd.Series,
    *,
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    calendar: TradingCalendar | str,
) -> None:
    """Pull admission: reject provider FX rates a Store Read could not cover."""
    _as_admission(
        lambda: assert_fx_history_coverage(
            pair,
            rates,
            timeframe=timeframe,
            start=start,
            end=end,
            calendar=calendar,
        )
    )


def _as_admission(check: Callable[[], None]) -> None:
    try:
        check()
    except StoreCoverageError as error:
        raise StoreAdmissionError(str(error)) from error


def _store_root(store_dir: Path | None) -> Path:
    return store_dir or data_dir()


def _read_one_fx_series(
    pair: FxPair,
    *,
    timeframe: str,
    calendar: TradingCalendar | str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    store_dir: Path | None,
) -> pd.Series:
    window = HistoryWindow(timeframe=timeframe, calendar=calendar, start=start, end=end)
    path = fx_history_path(pair, timeframe, store_dir=store_dir)
    admitted = _load_admitted_fx_history_or_empty(path)
    sliced = StoreCoverage.for_fx_rates(pair).slice(window, admitted)
    return sliced["rate"].copy()


def _native_bar_calendar(
    ref: InstrumentRef, calendar: TradingCalendar | str
) -> TradingCalendar:
    """The expected-bar calendar for a ref.

    A ``FuturesRef`` carries its venue in its dataset, so its calendar is resolved
    from that (CME/ICE), never the caller-supplied one — which governs only
    venue-agnostic refs (listed equities on XNYS).  This is why a futures Pull or
    Read needs no calendar threaded for the contract: the dataset decides it.
    """
    if isinstance(ref, FuturesRef):
        return venue_calendar_for_dataset(ref.dataset)
    return as_trading_calendar(calendar)


def _read_one_native_bar_frame(
    ref: InstrumentRef,
    *,
    arrays: tuple[str, ...],
    timeframe: str,
    listed_adjustment: ListedAdjustmentPolicy,
    calendar: TradingCalendar | str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    store_dir: Path | None,
) -> pd.DataFrame:
    window = HistoryWindow(
        timeframe=timeframe,
        calendar=_native_bar_calendar(ref, calendar),
        start=start,
        end=end,
    )
    path = native_bars_path(
        ref,
        timeframe,
        listed_adjustment=listed_adjustment,
        store_dir=store_dir,
    )
    return _read_admitted_native_bar_slice(
        ref,
        path,
        arrays=arrays,
        window=window,
    )


def _load_admitted_fx_history(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if "rate" not in frame.columns:
        raise StoreAdmissionError("FX History must contain a rate column")
    return _admit_fx_history(frame["rate"])


def _load_admitted_fx_history_or_empty(path: Path) -> pd.DataFrame:
    if path.exists():
        return _load_admitted_fx_history(path)
    return pd.DataFrame(columns=["rate"], index=pd.DatetimeIndex([]))


def _load_admitted_native_bars(path: Path) -> pd.DataFrame:
    return _admit_native_bars(pd.read_parquet(path))


def _load_admitted_native_bars_or_empty(path: Path, arrays: tuple[str, ...]) -> pd.DataFrame:
    if path.exists():
        return _load_admitted_native_bars(path)
    return pd.DataFrame(columns=list(arrays), index=pd.DatetimeIndex([]))


def _load_raw_futures_leg_coverage(path: Path) -> pd.DataFrame:
    return _admit_raw_futures_leg_coverage(pd.read_parquet(path))


def _write_admitted_native_bars(path: Path, admitted: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    admitted.to_parquet(path)
    return path


def _read_admitted_native_bar_slice(
    key: HistoryKey,
    path: Path,
    *,
    arrays: Sequence[str],
    window: HistoryWindow,
) -> pd.DataFrame:
    required = _validated_arrays(arrays)
    admitted = _load_admitted_native_bars_or_empty(path, required)
    return StoreCoverage.for_native_bars(key, arrays=required).slice(window, admitted)


def _read_raw_futures_leg_slice(
    leg: RawFuturesLeg,
    path: Path,
    *,
    arrays: Sequence[str],
    window: HistoryWindow,
    missing_ok: bool = False,
) -> pd.DataFrame:
    required = _validated_arrays(arrays)
    if path.exists():
        admitted = _load_admitted_native_bars(path)
    elif missing_ok:
        admitted = _load_admitted_native_bars_or_empty(path, required)
    else:
        raise StoreCoverageError(leg, f"no Raw Futures Leg for {window.timeframe}")
    columns = _require_native_bar_columns(leg, admitted, required)
    sliced = admitted.loc[(admitted.index >= window.start) & (admitted.index < window.end)]
    return select_history_columns(sliced, columns, required)


def _merge_admitted_native_bars(path: Path, admitted: pd.DataFrame) -> pd.DataFrame:
    existing = _load_admitted_native_bars(path)
    merged = existing.combine_first(admitted)
    return _admit_native_bars(merged)


def _merge_admitted_fx_history(path: Path, admitted: pd.DataFrame) -> pd.DataFrame:
    existing = _load_admitted_fx_history(path)
    merged = existing.combine_first(admitted)
    return _admit_fx_history(merged["rate"])


def _replace_admitted_native_bars(path: Path, admitted: pd.DataFrame) -> pd.DataFrame:
    existing = _load_admitted_native_bars(path)
    if admitted.empty:
        return existing
    left = admitted.index.min()
    right = admitted.index.max()
    outside = existing.loc[(existing.index < left) | (existing.index > right)]
    return _admit_native_bars(pd.concat([outside, admitted]).sort_index())


def _require_native_bar_columns(
    ref: HistoryKey,
    frame: pd.DataFrame,
    arrays: tuple[str, ...],
) -> dict[str, str]:
    columns = history_column_lookup(frame)
    missing_arrays = missing_history_columns(columns, arrays)
    if missing_arrays:
        raise StoreCoverageError(ref, f"missing arrays {list(missing_arrays)}")
    return columns


def _assert_admitted_native_bar_arrays(
    frame: pd.DataFrame,
    required_arrays: Sequence[str],
) -> None:
    required = _validated_arrays(required_arrays) if required_arrays else ()
    columns = history_column_lookup(frame)
    missing_arrays = missing_history_columns(columns, required)
    if missing_arrays:
        raise StoreAdmissionError(f"native bars missing required arrays {list(missing_arrays)}")


def _admit_raw_futures_leg_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in ("start", "end") if column not in frame.columns]
    if missing:
        raise StoreAdmissionError(f"Raw Futures Leg coverage missing columns {missing}")
    coverage = pd.DataFrame(
        {
            "start": [pd.Timestamp(value).tz_localize(None) for value in frame["start"]],
            "end": [pd.Timestamp(value).tz_localize(None) for value in frame["end"]],
        }
    )
    if (coverage["end"] <= coverage["start"]).any():
        raise StoreAdmissionError("Raw Futures Leg coverage end must be after start")
    return _coalesce_raw_futures_leg_coverage(coverage)


def _coalesce_raw_futures_leg_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values(["start", "end"])
    intervals: list[dict[str, pd.Timestamp]] = []
    for row in ordered.itertuples(index=False):
        start = pd.Timestamp(row.start)
        end = pd.Timestamp(row.end)
        if intervals and start <= intervals[-1]["end"]:
            intervals[-1]["end"] = max(intervals[-1]["end"], end)
            continue
        intervals.append({"start": start, "end": end})
    return pd.DataFrame(intervals, columns=["start", "end"])


def _admit_fx_history(rates: pd.Series) -> pd.DataFrame:
    admitted = _admit_datetime_indexed_history(rates, label="FX History")
    return admitted.rename("rate").to_frame()


def _admit_native_bars(bars: pd.DataFrame) -> pd.DataFrame:
    admitted = _admit_datetime_indexed_history(bars, label="native bars")
    if admitted.columns.has_duplicates:
        raise StoreAdmissionError("native bars contain duplicate columns")
    return admitted


def _admit_datetime_indexed_history(
    history: _HistoryFrame,
    *,
    label: str,
) -> _HistoryFrame:
    if not isinstance(history.index, pd.DatetimeIndex):
        raise StoreAdmissionError(f"{label} must be indexed by DatetimeIndex")
    if history.index.has_duplicates:
        raise StoreAdmissionError(f"{label} index contains duplicate timestamps")
    if history.index.is_monotonic_increasing:
        return history
    return history.sort_index()


def _listed_adjustment_policy(
    value: ListedAdjustmentPolicy | str,
) -> ListedAdjustmentPolicy:
    try:
        return ListedAdjustmentPolicy(value)
    except ValueError as error:
        allowed = [policy.value for policy in ListedAdjustmentPolicy]
        raise ValueError(
            f"unsupported listed adjustment policy {value!r}; expected one of {allowed}"
        ) from error


def _validated_arrays(arrays: Sequence[str]) -> tuple[str, ...]:
    values = tuple(str(array) for array in arrays)
    if not values:
        raise ValueError("Store Read requires at least one array")
    if any(not value for value in values):
        raise ValueError(f"Store Read arrays must be non-empty strings; got {values!r}")
    return values


def _safe_key(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)


__all__ = [
    "CoverageGap",
    "FxPair",
    "ListedAdjustmentPolicy",
    "NATIVE_OHLCV_ARRAYS",
    "NativeBarsRequest",
    "RawFuturesLeg",
    "StoreAdmissionError",
    "StoreCoverageError",
    "assert_admissible_fx_history",
    "assert_admissible_native_bars",
    "assert_fx_history_coverage",
    "assert_native_bar_coverage",
    "covered_row_count",
    "data_dir",
    "fx_history_coverage_gaps",
    "fx_history_path",
    "merge_fx_history",
    "merge_native_bars",
    "merge_raw_futures_leg",
    "native_bar_coverage_gaps",
    "native_bars_path",
    "raw_futures_leg_path",
    "raw_futures_dir",
    "read_fx_history",
    "read_native_bars",
    "read_native_bars_request",
    "read_raw_futures_leg",
    "read_raw_futures_leg_coverage",
    "read_raw_futures_leg_or_empty",
    "record_raw_futures_leg_coverage",
    "replace_native_bars",
    "write_fx_history",
    "write_native_bars",
]
