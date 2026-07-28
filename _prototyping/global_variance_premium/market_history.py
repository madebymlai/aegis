"""Ticker probing and per-market data loading, via the shared Yahoo Finance loader.

Reuses ``eu_variance_premium.yahoo_history``'s cache/fetch/validate machinery
(generalized there to take an arbitrary ticker — see that module's docstring) instead
of a second hand-rolled Yahoo Finance client. This module adds only what is specific to
the cross-market question: probing whether a candidate ticker is usable at all, and
pairing a market's volatility-index level series with its equity index's log returns.
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from _prototyping.eu_variance_premium import yahoo_history as yh

from .universe import MarketSpec


@dataclass(frozen=True)
class ProbeResult:
    """Whether one candidate ticker is retrievable via yfinance, and why not if not."""

    ticker: str
    available: bool
    start: str | None
    end: str | None
    observations: int
    detail: str


@dataclass(frozen=True)
class MarketData:
    """A market's paired implied-vol level series and equity log-return series."""

    label: str
    vol_ticker: str
    equity_ticker: str
    vol_level: pd.Series
    equity_log_returns: pd.Series
    vol_source: str
    equity_source: str


def probe_ticker(
    ticker: str,
    *,
    start: str = "1990-01-01",
    end: str | None = None,
    loader: yh.HistoryLoader = yh._yfinance_loader,
) -> ProbeResult:
    """Attempt to load ``ticker``'s close series and report whether it is usable.

    This is the empirical check the brief calls for — "establish which volatility
    indices are actually retrievable... do not assume, check" — kept runnable (via
    ``--probe``) rather than only recorded as a one-off README table that could go
    stale as Yahoo's coverage changes. ``loader`` is injectable, like every other
    Yahoo-touching function in this prototype, so tests can supply a canned frame
    instead of hitting the network. Every exception yfinance can raise for a bad or
    delisted ticker is caught deliberately here: this function's entire job is to turn
    "is this ticker retrievable" into a visible yes/no plus reason, not to enforce an
    internal invariant, so a broad catch is the right shape at this one boundary — the
    failure is reported in ``detail``, never swallowed.
    """
    try:
        loaded = yh.load_close_series(
            ticker, start, end or _today(), cache_dir=None, loader=loader
        )
    except Exception as error:  # noqa: BLE001 - reporting *why* a ticker failed is the point
        return ProbeResult(
            ticker, False, None, None, 0, f"{type(error).__name__}: {error}"
        )
    if loaded.observations == 0:
        return ProbeResult(ticker, False, None, None, 0, "empty series")
    return ProbeResult(
        ticker=ticker,
        available=True,
        start=loaded.series.index[0].date().isoformat(),
        end=loaded.series.index[-1].date().isoformat(),
        observations=loaded.observations,
        detail="ok",
    )


def load_market(
    spec: MarketSpec,
    *,
    start: str,
    end: str,
    cache_dir: Path | None,
    refresh: bool,
    loader: yh.HistoryLoader = yh._yfinance_loader,
) -> MarketData:
    """Load one market's vol-index level series and equity log-return series."""
    vol = yh.load_close_series(
        spec.vol_ticker, start, end, cache_dir=cache_dir, refresh=refresh, loader=loader
    )
    equity = yh.load_log_returns(
        spec.equity_ticker,
        start,
        end,
        cache_dir=cache_dir,
        refresh=refresh,
        loader=loader,
    )
    return MarketData(
        label=spec.label,
        vol_ticker=spec.vol_ticker,
        equity_ticker=spec.equity_ticker,
        vol_level=vol.series,
        equity_log_returns=equity.series,
        vol_source=vol.source,
        equity_source=equity.source,
    )


def _today() -> str:
    return _datetime.date.today().isoformat()
