"""YFinance Pull provider for listed native market bars and FX History."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd
from aegis_runtime import ListedRef

from aegis_data.calendars import TradingCalendar
from aegis_data.store import (
    FxPair,
    NATIVE_OHLCV_ARRAYS,
    NativeBarsRequest,
    assert_admissible_fx_history,
    assert_admissible_native_bars,
    covered_row_count,
    fx_history_coverage_gaps,
    fx_history_path,
    merge_fx_history,
    merge_native_bars,
    native_bar_coverage_gaps,
    native_bars_path,
)
from aegis_data.store_coverage import history_column_lookup, select_history_columns

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


@dataclass(frozen=True)
class FetchWindow:
    """Provider fetch window for one Pull request.

    Fetch input only: the window names the bars to download, never Historical
    Store identity. FX and listed Pulls share it so neither has to borrow a store
    request (or fabricate an identity) to express "fetch this span".
    """

    timeframe: str
    start: str | pd.Timestamp
    end: str | pd.Timestamp
    arrays: Sequence[str]


class YFinanceFetcher(Protocol):
    def __call__(
        self,
        locator: YFinanceLocator,
        window: FetchWindow,
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class PullResult:
    """Covered History admitted by a provider Pull."""

    ref: ListedRef
    locator: YFinanceLocator
    path: Path
    bars: int


@dataclass(frozen=True)
class PullFxResult:
    """FX History admitted by a provider Pull."""

    pair: FxPair
    locator: YFinanceLocator
    path: Path
    rates: int


def pull_yfinance_native_bars(
    request: NativeBarsRequest,
    locator: YFinanceLocator,
    *,
    fetcher: YFinanceFetcher | None = None,
    store_dir: Path | None = None,
) -> PullResult:
    """Fetch one listed instrument from yfinance and write native-bar Covered History."""
    ref = _single_listed_ref(request)
    fetch = fetcher or _fetch_yfinance
    gaps = native_bar_coverage_gaps(
        ref,
        arrays=request.arrays,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        calendar=request.calendar,
        listed_adjustment=request.listed_adjustment,
        store_dir=store_dir,
    )
    for gap in gaps:
        window = FetchWindow(
            timeframe=request.timeframe,
            start=gap.start,
            end=gap.end,
            arrays=request.arrays,
        )
        bars = _fetch_gap_bars(fetch, locator, window)
        assert_admissible_native_bars(
            ref,
            bars,
            arrays=window.arrays,
            timeframe=window.timeframe,
            start=window.start,
            end=window.end,
            calendar=request.calendar,
        )
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
    return PullResult(ref=ref, locator=locator, path=path, bars=covered_row_count(path))


def pull_yfinance_fx_history(
    pair: FxPair,
    *,
    timeframe: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    calendar: TradingCalendar | str,
    locator: YFinanceLocator,
    fetcher: YFinanceFetcher | None = None,
    store_dir: Path | None = None,
) -> PullFxResult:
    """Fetch one FX History series from yfinance and write Covered History."""
    fetch = fetcher or _fetch_yfinance
    gaps = fx_history_coverage_gaps(
        pair,
        timeframe=timeframe,
        start=start,
        end=end,
        calendar=calendar,
        store_dir=store_dir,
    )
    for gap in gaps:
        window = FetchWindow(timeframe=timeframe, start=gap.start, end=gap.end, arrays=("Close",))
        rates = _fetch_fx_gap_rates(fetch, locator, window)
        assert_admissible_fx_history(
            pair,
            rates,
            timeframe=window.timeframe,
            start=window.start,
            end=window.end,
            calendar=calendar,
        )
        merge_fx_history(pair, timeframe, rates, store_dir=store_dir)
    path = fx_history_path(pair, timeframe, store_dir=store_dir)
    return PullFxResult(pair=pair, locator=locator, path=path, rates=covered_row_count(path))


def _fetch_gap_bars(
    fetch: YFinanceFetcher,
    locator: YFinanceLocator,
    window: FetchWindow,
) -> pd.DataFrame:
    raw = fetch(locator, window)
    normalized = _normalize_yfinance_bars(raw)
    return _stored_yfinance_bars(normalized, window.arrays)


def _fetch_fx_gap_rates(
    fetch: YFinanceFetcher,
    locator: YFinanceLocator,
    window: FetchWindow,
) -> pd.Series:
    raw = fetch(locator, window)
    normalized = _normalize_yfinance_bars(raw)
    columns = history_column_lookup(normalized)
    if "close" not in columns:
        raise ValueError("yfinance FX History missing Close")
    return normalized[columns["close"]].rename("rate")


def _single_listed_ref(request: NativeBarsRequest) -> ListedRef:
    if len(request.refs) != 1:
        raise ValueError("yfinance Pull requires exactly one InstrumentRef")
    ref = request.refs[0]
    if not isinstance(ref, ListedRef):
        raise TypeError(f"yfinance Pull requires a ListedRef; got {ref!r}")
    return ref


def _fetch_yfinance(locator: YFinanceLocator, window: FetchWindow) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as error:  # pragma: no cover - exercised only without optional package
        raise RuntimeError("yfinance is required to Pull yfinance native bars") from error

    start = pd.Timestamp(window.start).date().isoformat()
    end = pd.Timestamp(window.end).date().isoformat()
    return yf.download(
        locator.ticker,
        start=start,
        end=end,
        interval=_yfinance_interval(window.timeframe),
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
    columns = history_column_lookup(frame)
    stored_arrays = _stored_yfinance_array_names(columns, requested_arrays)
    return select_history_columns(frame, columns, stored_arrays)


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
    "FetchWindow",
    "PullFxResult",
    "PullResult",
    "YFinanceFetcher",
    "YFinanceLocator",
    "pull_yfinance_fx_history",
    "pull_yfinance_native_bars",
]
