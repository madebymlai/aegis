"""OS-global parquet store for historical market data.

Per-contract pulls are cached as parquet under the OS user-data directory
(``platformdirs``), overridable with ``AEGIS_DATA_DIR``.  A repeated identical
request reads the parquet instead of re-hitting the provider — this is the
"``source:`` omitted means the cache path" default, shared by Aegis RD and Aegis
Trader (both read the same store).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias, TypeVar

import pandas as pd
import platformdirs
from aegis_runtime import FuturesRef, InstrumentRef, ListedRef

from aegis_data.chain import ContractFetcher

_APP = "aegis-data"
_DAILY_TIMEFRAMES = frozenset({"1D", "1d"})
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


HistoryKey: TypeAlias = InstrumentRef | FxPair


class StoreAdmissionError(ValueError):
    """Historical data cannot be admitted as Covered History."""


class StoreCoverageError(ValueError):
    """A provider-free Store Read cannot satisfy the requested Covered History."""

    def __init__(self, key: HistoryKey, detail: str) -> None:
        self.key = key
        super().__init__(f"{key.value}: {detail}")


@dataclass(frozen=True)
class NativeBarsRequest:
    """Neutral Covered History request for native market bars."""

    refs: Sequence[InstrumentRef]
    arrays: Sequence[str]
    timeframe: str
    start: str | date | pd.Timestamp
    end: str | date | pd.Timestamp
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW

    def __post_init__(self) -> None:
        refs = tuple(self.refs)
        if not refs:
            raise ValueError("NativeBarsRequest requires at least one InstrumentRef")
        object.__setattr__(self, "refs", refs)
        object.__setattr__(self, "arrays", _validated_arrays(self.arrays))
        if not self.timeframe:
            raise ValueError("NativeBarsRequest timeframe must be a non-empty string")
        object.__setattr__(
            self,
            "listed_adjustment",
            _listed_adjustment_policy(self.listed_adjustment),
        )
        _window(self.start, self.end)


def data_dir() -> Path:
    """The historical-data store root: ``$AEGIS_DATA_DIR`` or the OS user-data dir."""
    override = os.environ.get("AEGIS_DATA_DIR")
    return Path(override) if override else Path(platformdirs.user_data_dir(_APP))


def futures_dir(dataset: str, *, store_dir: Path | None = None) -> Path:
    return _store_root(store_dir) / "futures" / dataset


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
        return (
            root
            / "listed"
            / _safe_key(ref.figi)
            / "bars"
            / _safe_key(_listed_adjustment_policy(listed_adjustment).value)
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
    path.parent.mkdir(parents=True, exist_ok=True)
    admitted.to_parquet(path)
    return path


def read_native_bars(
    refs: Sequence[InstrumentRef],
    *,
    arrays: Sequence[str],
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    listed_adjustment: ListedAdjustmentPolicy | str = ListedAdjustmentPolicy.RAW,
    store_dir: Path | None = None,
) -> dict[InstrumentRef, pd.DataFrame]:
    """Provider-free Store Read for native market bars.

    Reads Covered History for each ``InstrumentRef`` and returns one native
    pandas frame per ref, sliced to ``[start, end)``.  Missing files, arrays,
    NaNs, or expected daily bars fail closed before a backtest can run.
    """
    return read_native_bars_request(
        NativeBarsRequest(
            refs=refs,
            arrays=arrays,
            timeframe=timeframe,
            start=start,
            end=end,
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
    start_ts, end_ts = _window(request.start, request.end)
    return {
        ref: _read_one_native_bar_frame(
            ref,
            arrays=tuple(request.arrays),
            timeframe=request.timeframe,
            listed_adjustment=_listed_adjustment_policy(request.listed_adjustment),
            start=start_ts,
            end=end_ts,
            store_dir=store_dir,
        )
        for ref in request.refs
    }


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


def read_fx_history(
    pairs: Sequence[FxPair],
    *,
    timeframe: str,
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
    store_dir: Path | None = None,
) -> dict[FxPair, pd.Series]:
    """Provider-free Store Read for FX History.

    Reads Covered History for each ``FxPair`` and returns one rate series per
    pair, sliced to ``[start, end)``. Missing files, NaNs, or expected daily FX
    rates fail closed before Trader valuation or conversion can run.
    """
    start_ts, end_ts = _window(start, end)
    return {
        pair: _read_one_fx_series(
            pair,
            timeframe=timeframe,
            start=start_ts,
            end=end_ts,
            store_dir=store_dir,
        )
        for pair in pairs
    }


def cached_fetcher(
    fetch: ContractFetcher, *, dataset: str, store_dir: Path | None = None
) -> ContractFetcher:
    """Wrap a per-contract fetcher with a write-through parquet cache in the store.

    Keyed by ``(symbol, start, end)``; on a miss it fetches and writes, then
    always returns the parquet-materialised frame (cache-hit and miss agree).
    """
    root = futures_dir(dataset, store_dir=store_dir)

    def cached(symbol: str, start: date, end: date) -> pd.DataFrame:
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{symbol}_{start.isoformat()}_{end.isoformat()}.parquet"
        if not path.exists():
            fetch(symbol, start, end).to_parquet(path)
        return pd.read_parquet(path)

    return cached


def _store_root(store_dir: Path | None) -> Path:
    return store_dir or data_dir()


def _read_one_fx_series(
    pair: FxPair,
    *,
    timeframe: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    store_dir: Path | None,
) -> pd.Series:
    path = fx_history_path(pair, timeframe, store_dir=store_dir)
    if not path.exists():
        raise StoreCoverageError(pair, f"no FX History for {timeframe}")
    admitted = _load_admitted_fx_history(path)
    sliced = _slice_window(admitted, start=start, end=end)
    _assert_expected_daily_coverage(
        pair, sliced, timeframe=timeframe, start=start, end=end, value_name="FX rate"
    )
    _assert_no_null_arrays(pair, sliced)
    return sliced["rate"].copy()


def _read_one_native_bar_frame(
    ref: InstrumentRef,
    *,
    arrays: tuple[str, ...],
    timeframe: str,
    listed_adjustment: ListedAdjustmentPolicy,
    start: pd.Timestamp,
    end: pd.Timestamp,
    store_dir: Path | None,
) -> pd.DataFrame:
    path = native_bars_path(
        ref,
        timeframe,
        listed_adjustment=listed_adjustment,
        store_dir=store_dir,
    )
    if not path.exists():
        raise StoreCoverageError(ref, f"no Covered History for {timeframe}")
    admitted = _load_admitted_native_bars(path)
    columns = _require_native_bar_columns(ref, admitted, arrays)
    sliced = _slice_window(admitted, start=start, end=end)
    _assert_expected_daily_coverage(ref, sliced, timeframe=timeframe, start=start, end=end)
    selected = _select_native_bar_arrays(sliced, columns, arrays)
    _assert_no_null_arrays(ref, selected)
    return selected


def _load_admitted_fx_history(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if "rate" not in frame.columns:
        raise StoreAdmissionError("FX History must contain a rate column")
    return _admit_fx_history(frame["rate"])


def _load_admitted_native_bars(path: Path) -> pd.DataFrame:
    return _admit_native_bars(pd.read_parquet(path))


def _require_native_bar_columns(
    ref: InstrumentRef,
    frame: pd.DataFrame,
    arrays: tuple[str, ...],
) -> dict[str, str]:
    columns = _column_lookup(frame)
    missing_arrays = tuple(array for array in arrays if array.lower() not in columns)
    if missing_arrays:
        raise StoreCoverageError(ref, f"missing arrays {list(missing_arrays)}")
    return columns


def _assert_admitted_native_bar_arrays(
    frame: pd.DataFrame,
    required_arrays: Sequence[str],
) -> None:
    required = _validated_arrays(required_arrays) if required_arrays else ()
    columns = _column_lookup(frame)
    missing_arrays = tuple(array for array in required if array.lower() not in columns)
    if missing_arrays:
        raise StoreAdmissionError(f"native bars missing required arrays {list(missing_arrays)}")


def _select_native_bar_arrays(
    frame: pd.DataFrame,
    columns: dict[str, str],
    arrays: tuple[str, ...],
) -> pd.DataFrame:
    selected = frame.loc[:, [columns[array.lower()] for array in arrays]].copy()
    selected.columns = list(arrays)
    return selected


def _slice_window(
    frame: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    return frame.loc[(frame.index >= start) & (frame.index < end)]


def _assert_no_null_arrays(key: HistoryKey, frame: pd.DataFrame) -> None:
    if frame.isna().any().any():
        raise StoreCoverageError(key, "requested arrays contain null values")


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


def _assert_expected_daily_coverage(
    key: HistoryKey,
    frame: pd.DataFrame,
    *,
    timeframe: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    value_name: str = "bar",
) -> None:
    if timeframe not in _DAILY_TIMEFRAMES:
        if frame.empty:
            raise StoreCoverageError(key, f"no {value_name}s in [{start.date()}, {end.date()})")
        return
    expected = _business_days(start, end)
    if expected.empty:
        return
    observed = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    missing = expected.difference(observed)
    if missing.empty:
        return
    first = missing[0].date().isoformat()
    raise StoreCoverageError(key, f"missing expected {timeframe} {value_name} on {first}")


def _business_days(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    last_inclusive = (end - pd.Timedelta(days=1)).normalize()
    if last_inclusive < start.normalize():
        return pd.DatetimeIndex([])
    return pd.bdate_range(start.normalize(), last_inclusive)


def _column_lookup(frame: pd.DataFrame) -> dict[str, str]:
    return {str(column).lower(): str(column) for column in frame.columns}


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


def _window(
    start: str | date | pd.Timestamp,
    end: str | date | pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    left = pd.Timestamp(start).tz_localize(None)
    right = pd.Timestamp(end).tz_localize(None)
    if right <= left:
        raise ValueError(f"Store Read end must be after start; got {start!r} -> {end!r}")
    return left, right


def _safe_key(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)


__all__ = [
    "FxPair",
    "ListedAdjustmentPolicy",
    "NATIVE_OHLCV_ARRAYS",
    "NativeBarsRequest",
    "StoreAdmissionError",
    "StoreCoverageError",
    "cached_fetcher",
    "data_dir",
    "futures_dir",
    "fx_history_path",
    "native_bars_path",
    "read_fx_history",
    "read_native_bars",
    "read_native_bars_request",
    "write_fx_history",
    "write_native_bars",
]
