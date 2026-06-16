"""Unit tests for the market-data snapshot cache (aegis-rd-34w).

The cache pins provider responses to disk so an identical backtest invocation is
byte-for-byte reproducible: the second fetch of the same request reads the pinned
bytes instead of re-hitting the (nondeterministic) live provider.
"""

from __future__ import annotations

import pandas as pd

from aegis_trader.backtest import BarRequest
from aegis_trader.data.snapshot import SnapshotCache


def _ohlcv_frame() -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    return pd.DataFrame(
        {"open": [1.0, 2.0, 3.0], "high": [1.5, 2.5, 3.5],
         "low": [0.5, 1.5, 2.5], "close": [1.2, 2.2, 3.2],
         "volume": [10, 20, 30]},
        index=idx,
    )


def _request(ticker: str = "IDTL.L") -> BarRequest:
    return BarRequest(
        ticker=ticker, required_arrays=("close",),
        start="2020-01-01", end="2020-01-04",
    )


def test_ohlcv_second_fetch_reads_the_pin_not_the_provider(tmp_path):
    """Read-through: first request calls the provider and pins it; an identical
    second request returns the pinned frame without calling the provider again."""
    calls = {"n": 0}
    frame = _ohlcv_frame()

    def provider(_request):
        calls["n"] += 1
        return frame

    cache = SnapshotCache(tmp_path)
    fetch = cache.ohlcv(provider)

    first = fetch(_request())
    second = fetch(_request())

    assert calls["n"] == 1  # provider hit once; the pin served the second call
    pd.testing.assert_frame_equal(first, frame)
    pd.testing.assert_frame_equal(second, frame)  # byte-identical round-trip


def test_distinct_requests_get_distinct_pins(tmp_path):
    """A different ticker or window keys to a different pin — no collision."""
    seen = []

    def provider(request):
        seen.append(request.ticker)
        return _ohlcv_frame()

    fetch = SnapshotCache(tmp_path).ohlcv(provider)
    fetch(_request("IDTL.L"))
    fetch(_request("IGLN.L"))  # different ticker
    fetch(BarRequest(ticker="IDTL.L", required_arrays=("close",),
                     start="2021-01-01", end="2021-01-04"))  # different window

    assert seen == ["IDTL.L", "IGLN.L", "IDTL.L"]  # each is a fresh provider call


def test_fx_second_fetch_reads_the_pin_not_the_provider(tmp_path):
    """The FX fetcher is pinned by (base, quote, window), same read-through rule."""
    calls = {"n": 0}
    series = pd.Series(
        [1.10, 1.11, 1.12], index=pd.date_range("2020-01-01", periods=3, freq="D")
    )

    def provider(base, quote, start, end):
        calls["n"] += 1
        return series

    fetch = SnapshotCache(tmp_path).fx(provider)
    first = fetch("EUR", "USD", "2020-01-01", "2020-01-04")
    second = fetch("EUR", "USD", "2020-01-01", "2020-01-04")

    assert calls["n"] == 1
    pd.testing.assert_series_equal(first, series)
    pd.testing.assert_series_equal(second, series)
