"""Integration tests for the backtest data loader (data/ load side).

Where MarketDataPort is the runtime READ side over the cache, this is the
backtest LOAD side: catalog OHLCV frames plus Nautilus instrument definitions
become Bars via the kernel's BarDataWrangler, ready to feed a BacktestEngine.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity

from aegis_trader.data import wrangle_bars

_INSTRUMENT_ID = InstrumentId.from_str("VUSA.XLON")


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


def test_wrangle_bars_turns_ohlcv_into_close_bars():
    instrument = _equity(_INSTRUMENT_ID, quote_currency="USD")

    bars = wrangle_bars(instrument, _ohlcv([100.0, 101.0, 102.0]), "1D")

    assert all(isinstance(b, Bar) for b in bars)
    assert len(bars) == 3
    assert [float(b.close.as_double()) for b in bars] == [100.0, 101.0, 102.0]
    assert bars[0].bar_type.instrument_id == instrument.id


def _equity(instrument_id: InstrumentId, *, quote_currency: str) -> Equity:
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        currency=Currency.from_str(quote_currency),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )
