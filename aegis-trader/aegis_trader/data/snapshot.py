"""Market-data snapshot cache — pins provider responses to disk so an identical
backtest invocation is byte-for-byte reproducible (aegis-rd-34w).

The live providers are nondeterministic: yfinance ``auto_adjust=True`` re-adjusts
the whole price history on every dividend/split, and live data shifts between
fetches, so the same backtest command returns different numbers run-to-run. This
cache decorates the injected ``fetch_ohlcv`` / ``fetch_fx`` seam: the first
request for a window calls the live provider and pins the response; every
identical later request reads the pinned bytes instead. Re-snapshot by clearing
the directory.

The on-disk format (one pickle per request, keyed by ticker/cross + window) is a
decision that lives only here — callers see plain fetchers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from aegis_trader.backtest import BarRequest, FxFetcher, OhlcvFetcher

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


class SnapshotCache:
    """A read-through disk cache for the provider fetchers, rooted at *directory*."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)

    def ohlcv(self, fetch: OhlcvFetcher) -> OhlcvFetcher:
        """Wrap an OHLCV fetcher so each ``BarRequest`` is pinned by ticker+window."""

        def cached(request: BarRequest) -> pd.DataFrame:
            key = f"ohlcv__{request.ticker}__{request.start}__{request.end}"
            return self._read_through(key, lambda: fetch(request))

        return cached

    def fx(self, fetch: FxFetcher) -> FxFetcher:
        """Wrap an FX fetcher so each (base, quote, window) cross is pinned."""

        def cached(base: str, quote: str, start: str, end: str) -> pd.Series:
            key = f"fx__{base}{quote}__{start}__{end}"
            return self._read_through(key, lambda: fetch(base, quote, start, end))

        return cached

    def _read_through(self, key: str, fetch):
        path = self._dir / f"{_UNSAFE.sub('_', key)}.pkl"
        if path.exists():
            return pd.read_pickle(path)
        value = fetch()
        self._dir.mkdir(parents=True, exist_ok=True)
        value.to_pickle(path)
        return value
