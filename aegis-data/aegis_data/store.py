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
from datetime import date
from pathlib import Path

import pandas as pd
import platformdirs
from aegis_runtime import FuturesRef, InstrumentRef, ListedRef

from aegis_data.chain import ContractFetcher

_APP = "aegis-data"
_DAILY_TIMEFRAMES = frozenset({"1D", "1d"})


class StoreAdmissionError(ValueError):
    """Native market data cannot be admitted as Covered History."""


class StoreCoverageError(ValueError):
    """A provider-free Store Read cannot satisfy the requested Covered History."""

    def __init__(self, ref: InstrumentRef, detail: str) -> None:
        self.ref = ref
        super().__init__(f"{ref.value}: {detail}")


def data_dir() -> Path:
    """The historical-data store root: ``$AEGIS_DATA_DIR`` or the OS user-data dir."""
    override = os.environ.get("AEGIS_DATA_DIR")
    return Path(override) if override else Path(platformdirs.user_data_dir(_APP))


def futures_dir(dataset: str, *, store_dir: Path | None = None) -> Path:
    return (store_dir or data_dir()) / "futures" / dataset


def native_bars_path(
    ref: InstrumentRef,
    timeframe: str,
    *,
    store_dir: Path | None = None,
) -> Path:
    """Parquet location for a native-market-bar Covered History slice.

    Listed instruments are keyed by ``ListedRef`` (FIGI), not by provider ticker.
    The path is intentionally exposed so tests can fixture-seed the Historical
    Store without introducing a provider.
    """
    if isinstance(ref, ListedRef):
        return (
            (store_dir or data_dir())
            / "listed"
            / _safe_key(ref.figi)
            / "bars"
            / f"{_safe_key(timeframe)}.parquet"
        )
    if isinstance(ref, FuturesRef):
        return (
            (store_dir or data_dir())
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
    store_dir: Path | None = None,
) -> Path:
    """Admit provider-normalized native market bars as Covered History.

    The frame is stored as-is apart from deterministic index sorting. Prices stay
    in the instrument's native quote currency; Store Read returns pandas frames,
    never Nautilus engine objects.
    """
    admitted = _admit_native_bars(bars)
    path = native_bars_path(ref, timeframe, store_dir=store_dir)
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
    store_dir: Path | None = None,
) -> dict[InstrumentRef, pd.DataFrame]:
    """Provider-free Store Read for native market bars.

    Reads Covered History for each ``InstrumentRef`` and returns one native
    pandas frame per ref, sliced to ``[start, end)``.  Missing files, arrays,
    NaNs, or expected daily bars fail closed before a backtest can run.
    """
    requested_arrays = _validated_arrays(arrays)
    window = _window(start, end)
    return {
        ref: _read_one_native_bar_frame(
            ref,
            arrays=requested_arrays,
            timeframe=timeframe,
            start=window[0],
            end=window[1],
            store_dir=store_dir,
        )
        for ref in refs
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


def _read_one_native_bar_frame(
    ref: InstrumentRef,
    *,
    arrays: tuple[str, ...],
    timeframe: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    store_dir: Path | None,
) -> pd.DataFrame:
    path = native_bars_path(ref, timeframe, store_dir=store_dir)
    if not path.exists():
        raise StoreCoverageError(ref, f"no Covered History for {timeframe}")
    stored = pd.read_parquet(path)
    admitted = _admit_native_bars(stored)
    columns = _column_lookup(admitted)
    missing_arrays = tuple(array for array in arrays if array.lower() not in columns)
    if missing_arrays:
        raise StoreCoverageError(ref, f"missing arrays {list(missing_arrays)}")
    sliced = admitted.loc[(admitted.index >= start) & (admitted.index < end)]
    _assert_expected_daily_coverage(ref, sliced, timeframe=timeframe, start=start, end=end)
    selected = sliced[[columns[array.lower()] for array in arrays]].copy()
    selected.columns = list(arrays)
    if selected.isna().any().any():
        raise StoreCoverageError(ref, "requested arrays contain null values")
    return selected


def _admit_native_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise StoreAdmissionError("native bars must be indexed by DatetimeIndex")
    if bars.index.has_duplicates:
        raise StoreAdmissionError("native bars index contains duplicate timestamps")
    if not bars.index.is_monotonic_increasing:
        bars = bars.sort_index()
    if bars.columns.has_duplicates:
        raise StoreAdmissionError("native bars contain duplicate columns")
    return bars


def _assert_expected_daily_coverage(
    ref: InstrumentRef,
    frame: pd.DataFrame,
    *,
    timeframe: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    if timeframe not in _DAILY_TIMEFRAMES:
        if frame.empty:
            raise StoreCoverageError(ref, f"no bars in [{start.date()}, {end.date()})")
        return
    expected = _business_days(start, end)
    if expected.empty:
        return
    observed = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    missing = expected.difference(observed)
    if missing.empty:
        return
    first = missing[0].date().isoformat()
    raise StoreCoverageError(ref, f"missing expected {timeframe} bar on {first}")


def _business_days(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    last_inclusive = (end - pd.Timedelta(days=1)).normalize()
    if last_inclusive < start.normalize():
        return pd.DatetimeIndex([])
    return pd.bdate_range(start.normalize(), last_inclusive)


def _column_lookup(frame: pd.DataFrame) -> dict[str, str]:
    return {str(column).lower(): str(column) for column in frame.columns}


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
    "StoreAdmissionError",
    "StoreCoverageError",
    "cached_fetcher",
    "data_dir",
    "futures_dir",
    "native_bars_path",
    "read_native_bars",
    "write_native_bars",
]
