"""YFinance Pull provider for listed native market bars and FX History."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd
from aegis_runtime import ListedRef

from aegis_data.calendars import TradingCalendar
from aegis_data.pull import FetchWindow as _FetchWindow
from aegis_data.pull import GapFetch, pull
from aegis_data.store import (
    CoveredWindow,
    FxPair,
    HistoricalStore,
    NATIVE_OHLCV_ARRAYS,
    NativeBarsRequest,
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


class YFinanceFetcher(Protocol):
    def __call__(
        self,
        locator: YFinanceLocator,
        window: _FetchWindow,
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class PullResult:
    """Covered History admitted by a provider Pull."""

    ref: ListedRef
    locator: YFinanceLocator


@dataclass(frozen=True)
class PullFxResult:
    """FX History admitted by a provider Pull."""

    pair: FxPair
    locator: YFinanceLocator


def yfinance_native_adapter(
    locator: YFinanceLocator,
    *,
    fetcher: YFinanceFetcher | None = None,
) -> GapFetch:
    """Return a yfinance GapFetch adapter bound to one Provider Locator."""
    fetch = fetcher or _fetch_yfinance

    def fetch_gap(window: _FetchWindow) -> pd.DataFrame:
        return _fetch_gap_bars(fetch, locator, window)

    return fetch_gap


def yfinance_fx_adapter(
    locator: YFinanceLocator,
    *,
    fetcher: YFinanceFetcher | None = None,
) -> GapFetch:
    """Return a yfinance FX GapFetch adapter bound to one Provider Locator."""
    fetch = fetcher or _fetch_yfinance

    def fetch_gap(window: _FetchWindow) -> pd.DataFrame:
        return _fetch_fx_gap_rates(
            fetch,
            locator,
            _FetchWindow(
                timeframe=window.timeframe,
                start=window.start,
                end=window.end,
                arrays=("Close",),
            ),
        )

    return fetch_gap


def pull_yfinance_native_bars(
    request: NativeBarsRequest,
    locator: YFinanceLocator,
    *,
    fetcher: YFinanceFetcher | None = None,
    store_dir: Path | None = None,
) -> PullResult:
    """Fetch one listed instrument from yfinance and write native-bar Covered History."""
    ref = _single_listed_ref(request)
    store = _store(store_dir)
    request_window = CoveredWindow(
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        arrays=request.arrays,
        calendar=request.calendar,
        listed_adjustment=request.listed_adjustment,
    )
    pull(
        ref,
        request_window,
        store=store,
        fetch=yfinance_native_adapter(locator, fetcher=fetcher),
    )
    return PullResult(ref=ref, locator=locator)


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
    store = _store(store_dir)
    request_window = CoveredWindow(
        timeframe=timeframe,
        start=start,
        end=end,
        arrays=("rate",),
        calendar=calendar,
    )
    pull(
        pair,
        request_window,
        store=store,
        fetch=yfinance_fx_adapter(locator, fetcher=fetcher),
    )
    return PullFxResult(pair=pair, locator=locator)


def _fetch_gap_bars(
    fetch: YFinanceFetcher,
    locator: YFinanceLocator,
    window: _FetchWindow,
) -> pd.DataFrame:
    raw = fetch(locator, window)
    normalized = _normalize_yfinance_bars(raw)
    return _stored_yfinance_bars(normalized, window.arrays)


def _fetch_fx_gap_rates(
    fetch: YFinanceFetcher,
    locator: YFinanceLocator,
    window: _FetchWindow,
) -> pd.DataFrame:
    raw = fetch(locator, window)
    normalized = _normalize_yfinance_bars(raw)
    columns = history_column_lookup(normalized)
    if "close" not in columns:
        raise ValueError("yfinance FX History missing Close")
    return normalized[columns["close"]].rename("rate").to_frame()


def _store(store_dir: Path | None) -> HistoricalStore:
    return HistoricalStore(store_dir) if store_dir is not None else HistoricalStore()


def _single_listed_ref(request: NativeBarsRequest) -> ListedRef:
    if len(request.refs) != 1:
        raise ValueError("yfinance Pull requires exactly one InstrumentRef")
    ref = request.refs[0]
    if not isinstance(ref, ListedRef):
        raise TypeError(f"yfinance Pull requires a ListedRef; got {ref!r}")
    return ref


def _fetch_yfinance(locator: YFinanceLocator, window: _FetchWindow) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as error:  # pragma: no cover - optional package
        raise RuntimeError("yfinance is required to Pull yfinance history") from error

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


def _stored_yfinance_bars(
    frame: pd.DataFrame, requested_arrays: Sequence[str]
) -> pd.DataFrame:
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
    "PullFxResult",
    "PullResult",
    "YFinanceFetcher",
    "YFinanceLocator",
    "pull_yfinance_fx_history",
    "pull_yfinance_native_bars",
    "yfinance_fx_adapter",
    "yfinance_native_adapter",
]
