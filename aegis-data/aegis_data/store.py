"""OS-global parquet store for historical market data.

Provider-normalized history is stored as a reusable corpus under the OS
user-data directory (``platformdirs``), overridable with ``AEGIS_DATA_DIR``.
Store Reads are coverage-based, and Pulls can fill only instrument-calendar Gaps
instead of re-fetching already covered intervals.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import TypeVar

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


class WriteMode(StrEnum):
    """Covered History write semantics."""

    MERGE = "merge"
    REPLACE = "replace"
    OVERWRITE = "overwrite"


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


@dataclass(frozen=True)
class CoveredWindow:
    """Covered History demand over one half-open window."""

    timeframe: str
    start: str | date | pd.Timestamp
    end: str | date | pd.Timestamp
    arrays: Sequence[str]
    calendar: TradingCalendar | str
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW

    def __post_init__(self) -> None:
        history_window = HistoryWindow(
            timeframe=self.timeframe,
            calendar=self.calendar,
            start=self.start,
            end=self.end,
        )
        object.__setattr__(self, "start", history_window.start)
        object.__setattr__(self, "end", history_window.end)
        object.__setattr__(self, "calendar", history_window.calendar)
        object.__setattr__(self, "arrays", _validated_arrays(self.arrays))
        object.__setattr__(
            self,
            "listed_adjustment",
            _listed_adjustment_policy(self.listed_adjustment),
        )

    def narrowed_to(self, gap: CoverageGap) -> CoveredWindow:
        """Return this window narrowed to one coverage gap."""
        return CoveredWindow(
            timeframe=self.timeframe,
            start=gap.start,
            end=gap.end,
            arrays=self.arrays,
            calendar=self.calendar,
            listed_adjustment=self.listed_adjustment,
        )

    def _history_window(self, *, calendar: TradingCalendar | str) -> HistoryWindow:
        """Build the StoreCoverage window using the effective calendar."""
        return HistoryWindow(
            timeframe=self.timeframe,
            calendar=calendar,
            start=self.start,
            end=self.end,
        )


def data_dir() -> Path:
    """The historical-data store root: ``$AEGIS_DATA_DIR`` or the OS user-data dir."""
    override = os.environ.get("AEGIS_DATA_DIR")
    return Path(override) if override else Path(platformdirs.user_data_dir(_APP))


@dataclass(frozen=True)
class HistoricalStore:
    """Deep Historical Store interface for one store root."""

    root: Path = field(default_factory=data_dir)

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))

    def read(
        self,
        key: InstrumentRef | FxPair,
        window: CoveredWindow,
    ) -> pd.DataFrame:
        """Provider-free Store Read for one Covered History identity."""
        coverage_window = self._coverage_window(key, window)
        path = self._path(key, window)
        if isinstance(key, FxPair):
            self._require_fx_rate_array(key, window)
            admitted = _load_admitted_fx_history_or_empty(path)
            return StoreCoverage.for_fx_rates(key).slice(coverage_window, admitted)
        return _read_admitted_native_bar_slice(
            key,
            path,
            arrays=window.arrays,
            window=coverage_window,
        )

    def write(
        self,
        key: InstrumentRef | FxPair,
        value: pd.DataFrame,
        window: CoveredWindow,
        *,
        mode: WriteMode | str,
    ) -> None:
        """Admit and write one Covered History frame."""
        write_mode = WriteMode(mode)
        path = self._path(key, window)
        if isinstance(key, FxPair):
            self._require_fx_rate_array(key, window)
            admitted = _admit_fx_history_frame(value)
            merged = self._merge_write(path, admitted, write_mode, _load_admitted_fx_history)
            path.parent.mkdir(parents=True, exist_ok=True)
            merged.to_parquet(path)
            return
        admitted = _admit_native_bars(value)
        _assert_admitted_native_bar_arrays(admitted, window.arrays)
        merged = self._merge_write(path, admitted, write_mode, _load_admitted_native_bars)
        _write_admitted_native_bars(path, merged)

    def coverage_gaps(
        self,
        key: InstrumentRef | FxPair,
        window: CoveredWindow,
    ) -> tuple[CoverageGap, ...]:
        """Return uncovered expected intervals for one Covered History identity."""
        coverage_window = self._coverage_window(key, window)
        path = self._path(key, window)
        if isinstance(key, FxPair):
            self._require_fx_rate_array(key, window)
            observed = _load_admitted_fx_history_or_empty(path)
            return StoreCoverage.for_fx_rates(key).gaps(coverage_window, observed)
        observed = _load_admitted_native_bars_or_empty(path, tuple(window.arrays))
        return StoreCoverage.for_native_bars(key, arrays=window.arrays).gaps(
            coverage_window,
            observed,
        )

    def assert_admissible(
        self,
        key: InstrumentRef | FxPair,
        value: pd.DataFrame,
        window: CoveredWindow,
    ) -> None:
        """Pull admission: reject a provider frame that cannot cover the window."""
        coverage_window = self._coverage_window(key, window)
        try:
            if isinstance(key, FxPair):
                self._require_fx_rate_array(key, window)
                admitted = _admit_fx_history_frame(value)
                StoreCoverage.for_fx_rates(key).slice(coverage_window, admitted)
                return
            admitted = _admit_native_bars(value)
            StoreCoverage.for_native_bars(key, arrays=window.arrays).slice(
                coverage_window,
                admitted,
            )
        except StoreCoverageError as error:
            raise StoreAdmissionError(str(error)) from error

    def merge_leg(
        self,
        leg: RawFuturesLeg,
        value: pd.DataFrame,
        window: CoveredWindow,
    ) -> None:
        """Merge Raw Futures Leg source material without exposing overwrite modes."""
        admitted = _admit_native_bars(value)
        _assert_admitted_native_bar_arrays(admitted, window.arrays)
        path = self._leg_path(leg, window.timeframe)
        merged = _merge_admitted_native_bars(path, admitted) if path.exists() else admitted
        _write_admitted_native_bars(path, merged)

    def read_leg(
        self,
        leg: RawFuturesLeg,
        window: CoveredWindow,
    ) -> pd.DataFrame:
        """Read Raw Futures Leg source material, returning empty on a cold leg."""
        return _read_raw_futures_leg_slice(
            leg,
            self._leg_path(leg, window.timeframe),
            arrays=window.arrays,
            window=window._history_window(calendar=window.calendar),
            missing_ok=True,
        )

    def record_leg_coverage(self, leg: RawFuturesLeg, window: CoveredWindow) -> None:
        """Remember a fetched Raw Futures Leg window, even when it had no bars."""
        coverage = _admit_raw_futures_leg_coverage(
            pd.DataFrame({"start": [window.start], "end": [window.end]})
        )
        path = self._leg_coverage_path(leg, window.timeframe)
        if path.exists():
            coverage = _coalesce_raw_futures_leg_coverage(
                pd.concat([_load_raw_futures_leg_coverage(path), coverage])
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        coverage.to_parquet(path)

    def read_leg_coverage(
        self,
        leg: RawFuturesLeg,
        *,
        timeframe: str,
    ) -> tuple[CoverageGap, ...]:
        """Fetched half-open Raw Futures Leg windows for cache decisions."""
        path = self._leg_coverage_path(leg, timeframe)
        if not path.exists():
            return ()
        coverage = _load_raw_futures_leg_coverage(path)
        return tuple(
            CoverageGap(start=row.start, end=row.end)
            for row in coverage.itertuples(index=False)
        )

    def _path(
        self,
        key: InstrumentRef | FxPair,
        window: CoveredWindow,
    ) -> Path:
        return _covered_history_path(
            key,
            window.timeframe,
            listed_adjustment=window.listed_adjustment,
            store_dir=self.root,
        )

    def _leg_path(self, leg: RawFuturesLeg, timeframe: str) -> Path:
        return (
            raw_futures_dir(leg.dataset, store_dir=self.root)
            / _safe_key(leg.symbol)
            / f"{_safe_key(timeframe)}.parquet"
        )

    def _leg_coverage_path(self, leg: RawFuturesLeg, timeframe: str) -> Path:
        return (
            raw_futures_dir(leg.dataset, store_dir=self.root)
            / _safe_key(leg.symbol)
            / ".coverage"
            / f"{_safe_key(timeframe)}.parquet"
        )

    def _coverage_window(
        self,
        key: InstrumentRef | FxPair,
        window: CoveredWindow,
    ) -> HistoryWindow:
        if isinstance(key, FuturesRef):
            return window._history_window(calendar=venue_calendar_for_dataset(key.dataset))
        if isinstance(key, (ListedRef, FxPair)):
            return window._history_window(calendar=window.calendar)
        raise TypeError(f"unsupported HistoricalStore key {key!r}")

    def _require_fx_rate_array(self, key: FxPair, window: CoveredWindow) -> None:
        missing = missing_history_columns({"rate": "rate"}, window.arrays)
        if missing:
            raise StoreCoverageError(key, f"missing arrays {list(missing)}")

    def _merge_write(
        self,
        path: Path,
        admitted: pd.DataFrame,
        mode: WriteMode,
        load_existing: Callable[[Path], pd.DataFrame],
    ) -> pd.DataFrame:
        if mode is WriteMode.OVERWRITE or not path.exists():
            return admitted
        if mode is WriteMode.MERGE:
            return _admit_covered_frame(load_existing(path).combine_first(admitted))
        return _replace_admitted_frame(load_existing(path), admitted)


def raw_futures_dir(dataset: str, *, store_dir: Path | None = None) -> Path:
    return _store_root(store_dir) / "futures-raw" / _safe_key(dataset)


def _store_root(store_dir: Path | None) -> Path:
    return store_dir or data_dir()


def _covered_history_path(
    key: InstrumentRef | FxPair,
    timeframe: str,
    *,
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW,
    store_dir: Path | None = None,
) -> Path:
    root = _store_root(store_dir)
    if isinstance(key, FxPair):
        return (
            root
            / "fx"
            / _safe_key(key.base)
            / _safe_key(key.quote)
            / f"{_safe_key(timeframe)}.parquet"
        )
    if isinstance(key, ListedRef):
        adjustment = _listed_adjustment_policy(listed_adjustment)
        return (
            root
            / "listed"
            / _safe_key(key.figi)
            / "bars"
            / _safe_key(adjustment.value)
            / f"{_safe_key(timeframe)}.parquet"
        )
    if isinstance(key, FuturesRef):
        return (
            root
            / "futures-ref"
            / _safe_key(key.dataset)
            / _safe_key(key.root)
            / _safe_key(key.roll_rule)
            / f"{_safe_key(key.adjustment)}_{_safe_key(timeframe)}.parquet"
        )
    raise TypeError(f"unsupported HistoricalStore key {key!r}")


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
    key: InstrumentRef | RawFuturesLeg,
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


def _replace_admitted_frame(existing: pd.DataFrame, admitted: pd.DataFrame) -> pd.DataFrame:
    if admitted.empty:
        return existing
    left = admitted.index.min()
    right = admitted.index.max()
    outside = existing.loc[(existing.index < left) | (existing.index > right)]
    return _admit_covered_frame(pd.concat([outside, admitted]).sort_index())


def _admit_covered_frame(frame: pd.DataFrame) -> pd.DataFrame:
    admitted = _admit_datetime_indexed_history(frame, label="Covered History")
    if admitted.columns.has_duplicates:
        raise StoreAdmissionError("Covered History contains duplicate columns")
    return admitted


def _require_native_bar_columns(
    ref: InstrumentRef | RawFuturesLeg,
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


def _admit_fx_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise StoreAdmissionError("FX History must be a rate-column DataFrame")
    if "rate" not in frame.columns:
        raise StoreAdmissionError("FX History must contain a rate column")
    return _admit_fx_history(frame["rate"])


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
    "CoveredWindow",
    "CoverageGap",
    "FxPair",
    "HistoricalStore",
    "ListedAdjustmentPolicy",
    "NATIVE_OHLCV_ARRAYS",
    "NativeBarsRequest",
    "RawFuturesLeg",
    "StoreAdmissionError",
    "StoreCoverageError",
    "WriteMode",
    "data_dir",
    "raw_futures_dir",
]
