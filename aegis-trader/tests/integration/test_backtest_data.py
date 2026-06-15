"""Integration tests for the backtest data loader (data/ load side).

Where MarketDataPort is the runtime READ side over the cache, this is the
backtest LOAD side: provider-agnostic OHLCV frames become Nautilus instruments
and Bars via the kernel's BarDataWrangler, ready to feed a BacktestEngine.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.instruments import Equity

from aegis_trader.data import InstrumentSpec, build_equity, wrangle_bars

_FIGI = "BBG0022FR5K6"


def _ohlcv(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000] * len(closes),
        },
        index=idx,
    )


def test_build_equity_keys_instrument_by_figi_and_venue():
    spec = InstrumentSpec(figi=_FIGI, venue="XLON", quote_currency="USD")

    instrument = build_equity(spec)

    assert isinstance(instrument, Equity)
    assert instrument.id.value == f"{_FIGI}.XLON"
    assert instrument.quote_currency.code == "USD"


def test_wrangle_bars_turns_ohlcv_into_close_bars():
    instrument = build_equity(InstrumentSpec(figi=_FIGI, venue="XLON", quote_currency="USD"))

    bars = wrangle_bars(instrument, _ohlcv([100.0, 101.0, 102.0]), "1D")

    assert all(isinstance(b, Bar) for b in bars)
    assert len(bars) == 3
    assert [float(b.close.as_double()) for b in bars] == [100.0, 101.0, 102.0]
    # The bar type carries the instrument's FIGI.venue id (the overlay keys on it).
    assert bars[0].bar_type.instrument_id == instrument.id
