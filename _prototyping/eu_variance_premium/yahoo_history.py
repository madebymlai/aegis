"""Free daily history for any Yahoo Finance ticker (``yfinance``), close levels or
log returns.

``yfinance`` is already an aegis-rd dependency (used elsewhere as the FX gap-fill
provider), so this reuses it rather than hand-rolling a Yahoo scraper. The loader is
injected so tests can supply canned frames without touching the network — the actual
HTTP call is the one thing in this module we cannot verify offline.

Originally written just for EURO STOXX 50 (``load_sx5e_log_returns``, kept below as a
thin wrapper so this prototype's own README/tests/``__main__.py`` don't have to change).
``load_close_series``/``load_log_returns`` generalize the same cache-then-fetch-then-
validate machinery to an arbitrary ticker, so the sibling ``global_variance_premium``
prototype can load other markets' volatility-index levels and equity-index returns
through this one module instead of a second hand-rolled Yahoo loader.

VSTOXX is *not* here regardless: Yahoo carries no VSTOXX ticker at all (see
``stoxx_history.py``), and no free full-history investable EURO STOXX 50 put-write
series was found either (see README.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SX5E_TICKER = "^STOXX50E"

HistoryLoader = Callable[[str, str, str], pd.DataFrame]


class MarketDataError(ValueError):
    """A fetched series fails the schema or sanity checks this test depends on."""


@dataclass(frozen=True)
class SeriesLoad:
    series: pd.Series
    ticker: str
    start: str
    end: str
    observations: int
    source: str  # "cache" or "live"


def _yfinance_loader(ticker: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    return yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)


def load_sx5e_log_returns(
    start: str,
    end: str,
    *,
    cache_dir: Path | None = None,
    loader: HistoryLoader = _yfinance_loader,
    refresh: bool = False,
) -> SeriesLoad:
    """EURO STOXX 50 daily log returns — thin wrapper over ``load_log_returns``.

    Kept as its own function (rather than inlining the ticker at call sites) so this
    prototype's README, tests, and ``__main__.py`` keep the name they already document.
    """
    return load_log_returns(
        SX5E_TICKER, start, end, cache_dir=cache_dir, loader=loader, refresh=refresh
    )


def load_close_series(
    ticker: str,
    start: str,
    end: str,
    *,
    cache_dir: Path | None = None,
    loader: HistoryLoader = _yfinance_loader,
    refresh: bool = False,
) -> SeriesLoad:
    """Load any ticker's daily close level series, validated and de-duplicated.

    Used directly for series that are levels, not returns — e.g. a volatility index
    quoted in vol points, which is meaningless as a log return.
    """
    frame, source = _load_cached_or_live(ticker, start, end, cache_dir, loader, refresh)
    close = _closes(frame, ticker)
    return SeriesLoad(close, ticker, start, end, len(close), source)


def load_log_returns(
    ticker: str,
    start: str,
    end: str,
    *,
    cache_dir: Path | None = None,
    loader: HistoryLoader = _yfinance_loader,
    refresh: bool = False,
    max_abs_log_return: float = 0.25,
) -> SeriesLoad:
    """Load any ticker's daily log returns, validated as plausible single-day moves."""
    closes = load_close_series(
        ticker, start, end, cache_dir=cache_dir, loader=loader, refresh=refresh
    )
    log_returns = np.log(closes.series).diff().dropna()
    if log_returns.abs().max() > max_abs_log_return:
        raise MarketDataError(
            f"{ticker} has a single-day log return exceeding {max_abs_log_return:.0%}; "
            "check for a bad print or stock-split-style artifact"
        )
    return SeriesLoad(log_returns, ticker, start, end, len(log_returns), closes.source)


def _closes(frame: pd.DataFrame, ticker: str) -> pd.Series:
    if frame.empty or "Close" not in frame.columns:
        raise MarketDataError(f"{ticker}: no usable 'Close' column returned")
    close = frame["Close"].copy()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    close = close.dropna()
    if close.empty:
        raise MarketDataError(f"{ticker}: history is empty after cleaning")
    if not (close > 0.0).all():
        raise MarketDataError(f"{ticker}: history contains non-positive values")
    return close


def _load_cached_or_live(
    ticker: str,
    start: str,
    end: str,
    cache_dir: Path | None,
    loader: HistoryLoader,
    refresh: bool,
) -> tuple[pd.DataFrame, str]:
    cache_path = (
        None if cache_dir is None else cache_dir / f"{_cache_key(ticker)}.parquet"
    )
    if cache_path is not None and cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path), "cache"
    frame = loader(ticker, start, end)
    if cache_path is not None and isinstance(frame, pd.DataFrame) and not frame.empty:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(cache_path)
    return frame, "live"


def _cache_key(ticker: str) -> str:
    return ticker.replace("^", "").replace(".", "_")
