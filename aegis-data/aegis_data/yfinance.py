"""YFinance Pull provider for listed native market bars."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd
from aegis_runtime import ListedRef

from aegis_data.store import (
    NATIVE_OHLCV_ARRAYS,
    NativeBarsRequest,
    StoreAdmissionError,
    StoreCoverageError,
    assert_native_bar_coverage,
    merge_native_bars,
    native_bar_coverage_gaps,
    native_bars_path,
)

_MULTIPLE_SYMBOLS_ERROR = "yfinance Pull for one ListedRef returned multiple symbols"
_YFINANCE_PRICE_FIELDS = frozenset({"Open", "Close"})


@dataclass(frozen=True)
class YFinanceLocator:
    """Provider Locator for yfinance ticker text.

    The locator is fetch input only.  It is never used as Historical Store
    identity; callers must provide a ``ListedRef`` in the neutral request.
    """

    ticker: str

    def __post_init__(self) -> None:
        if not isinstance(self.ticker, str) or not self.ticker:
            raise ValueError(
                f"YFinanceLocator ticker must be a non-empty string; got {self.ticker!r}"
            )


class YFinanceFetcher(Protocol):
    def __call__(
        self,
        locator: YFinanceLocator,
        request: NativeBarsRequest,
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class PullResult:
    """Covered History admitted by a provider Pull."""

    ref: ListedRef
    locator: YFinanceLocator
    path: Path
    bars: int


def pull_yfinance_native_bars(
    request: NativeBarsRequest,
    locator: YFinanceLocator,
    *,
    fetcher: YFinanceFetcher | None = None,
    store_dir: Path | None = None,
) -> PullResult:
    """Fetch one listed instrument from yfinance and write native-bar Covered History."""
    ref = _single_listed_ref(request)
    gaps = native_bar_coverage_gaps(
        ref,
        arrays=request.arrays,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        listed_adjustment=request.listed_adjustment,
        store_dir=store_dir,
    )
    for gap in gaps:
        gap_request = NativeBarsRequest(
            refs=(ref,),
            arrays=request.arrays,
            timeframe=request.timeframe,
            start=gap.start,
            end=gap.end,
            listed_adjustment=request.listed_adjustment,
        )
        raw = (fetcher or _fetch_yfinance)(locator, gap_request)
        bars = _stored_yfinance_bars(_normalize_yfinance_bars(raw), request.arrays)
        _assert_pulled_gap_coverage(ref, bars, gap_request)
        merge_native_bars(
            ref,
            request.timeframe,
            bars,
            listed_adjustment=request.listed_adjustment,
            required_arrays=request.arrays,
            store_dir=store_dir,
        )
    path = native_bars_path(
        ref,
        request.timeframe,
        listed_adjustment=request.listed_adjustment,
        store_dir=store_dir,
    )
    return PullResult(ref=ref, locator=locator, path=path, bars=_covered_bar_count(path))


def _single_listed_ref(request: NativeBarsRequest) -> ListedRef:
    if len(request.refs) != 1:
        raise ValueError("yfinance Pull requires exactly one InstrumentRef")
    ref = request.refs[0]
    if not isinstance(ref, ListedRef):
        raise TypeError(f"yfinance Pull requires a ListedRef; got {ref!r}")
    return ref


def _assert_pulled_gap_coverage(
    ref: ListedRef,
    bars: pd.DataFrame,
    request: NativeBarsRequest,
) -> None:
    try:
        assert_native_bar_coverage(
            ref,
            bars,
            arrays=request.arrays,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
        )
    except StoreCoverageError as error:
        raise StoreAdmissionError(str(error)) from error


def _covered_bar_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(pd.read_parquet(path))


def _fetch_yfinance(locator: YFinanceLocator, request: NativeBarsRequest) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as error:  # pragma: no cover - exercised only without optional package
        raise RuntimeError("yfinance is required to Pull yfinance native bars") from error

    start = pd.Timestamp(request.start).date().isoformat()
    end = pd.Timestamp(request.end).date().isoformat()
    return yf.download(
        locator.ticker,
        start=start,
        end=end,
        interval=_yfinance_interval(request.timeframe),
        auto_adjust=False,
        actions=False,
        progress=False,
        threads=False,
    )


def _normalize_yfinance_bars(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        raise ValueError("yfinance returned no bars")
    if isinstance(frame.columns, pd.MultiIndex):
        frame = _single_symbol_yfinance_frame(frame)
    normalized = frame.copy()
    normalized.index = pd.DatetimeIndex(normalized.index).tz_localize(None).normalize()
    return normalized


def _stored_yfinance_bars(frame: pd.DataFrame, requested_arrays: Sequence[str]) -> pd.DataFrame:
    columns = _column_lookup(frame)
    stored_arrays = _stored_yfinance_array_names(columns, requested_arrays)
    selected = frame.loc[:, [columns[array.lower()] for array in stored_arrays]].copy()
    selected.columns = list(stored_arrays)
    return selected


def _stored_yfinance_array_names(
    columns: dict[str, str],
    requested_arrays: Sequence[str],
) -> tuple[str, ...]:
    stored_arrays = list(_available_arrays(columns, NATIVE_OHLCV_ARRAYS))
    stored_array_keys = {array.lower() for array in stored_arrays}
    for requested_array in requested_arrays:
        requested_key = requested_array.lower()
        if requested_key not in columns or requested_key in stored_array_keys:
            continue
        stored_arrays.append(requested_array)
        stored_array_keys.add(requested_key)
    return tuple(stored_arrays)


def _available_arrays(
    columns: dict[str, str],
    arrays: Sequence[str],
) -> tuple[str, ...]:
    return tuple(array for array in arrays if array.lower() in columns)


def _column_lookup(frame: pd.DataFrame) -> dict[str, str]:
    return {str(column).lower(): str(column) for column in frame.columns}


def _single_symbol_yfinance_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.columns.nlevels != 2:
        raise ValueError("yfinance returned an unsupported multi-index column layout")
    symbol_level = _yfinance_symbol_level(frame)
    symbol = _single_symbol_value(frame, level=symbol_level)
    return frame.xs(symbol, axis=1, level=symbol_level)


def _yfinance_symbol_level(frame: pd.DataFrame) -> int:
    first_level = frame.columns.get_level_values(0)
    if any(field in _YFINANCE_PRICE_FIELDS for field in first_level):
        return 1
    return 0


def _single_symbol_value(frame: pd.DataFrame, *, level: int) -> object:
    symbol_values = tuple(dict.fromkeys(frame.columns.get_level_values(level)))
    if len(symbol_values) != 1:
        raise ValueError(_MULTIPLE_SYMBOLS_ERROR)
    return symbol_values[0]


def _yfinance_interval(timeframe: str) -> str:
    if timeframe in {"1D", "1d"}:
        return "1d"
    return timeframe


__all__ = [
    "PullResult",
    "YFinanceFetcher",
    "YFinanceLocator",
    "pull_yfinance_native_bars",
]
