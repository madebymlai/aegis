"""YFinance Pull provider for listed native market bars."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd
from aegis_runtime import ListedRef

from aegis_data.store import NativeBarsRequest, write_native_bars


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
    def __call__(self, locator: YFinanceLocator, request: NativeBarsRequest) -> pd.DataFrame: ...


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
    raw = (fetcher or _fetch_yfinance)(locator, request)
    bars = _normalize_yfinance_bars(raw)
    path = write_native_bars(ref, request.timeframe, bars, store_dir=store_dir)
    return PullResult(ref=ref, locator=locator, path=path, bars=len(bars))


def _single_listed_ref(request: NativeBarsRequest) -> ListedRef:
    if len(request.refs) != 1:
        raise ValueError("yfinance Pull requires exactly one InstrumentRef")
    ref = request.refs[0]
    if not isinstance(ref, ListedRef):
        raise TypeError(f"yfinance Pull requires a ListedRef; got {ref!r}")
    return ref


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
    normalized = normalized.rename(columns={"Adj Close": "Adj Close"})
    return normalized


def _single_symbol_yfinance_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.columns.nlevels != 2:
        raise ValueError("yfinance returned an unsupported multi-index column layout")
    first_level = frame.columns.get_level_values(0)
    if "Open" in first_level or "Close" in first_level:
        symbol_values = tuple(dict.fromkeys(frame.columns.get_level_values(1)))
        if len(symbol_values) != 1:
            raise ValueError("yfinance Pull for one ListedRef returned multiple symbols")
        return frame.xs(symbol_values[0], axis=1, level=1)
    symbol_values = tuple(dict.fromkeys(frame.columns.get_level_values(0)))
    if len(symbol_values) != 1:
        raise ValueError("yfinance Pull for one ListedRef returned multiple symbols")
    return frame.xs(symbol_values[0], axis=1, level=0)


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
