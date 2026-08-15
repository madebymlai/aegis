"""Integration tests for the backtest data loader (data/ load side).

Where MarketDataPort is the runtime READ side over the cache, this is the
backtest LOAD side: catalog OHLCV frames plus Nautilus instrument definitions
become Bars via the kernel's BarDataWrangler, ready to feed a BacktestEngine.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import Bar, QuoteTick
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair, Equity
from nautilus_trader.model.objects import Currency, Price, Quantity

from aegis_trader.data import build_currency_pair, wrangle_bars, wrangle_fx_quotes

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


def test_wrangle_fx_quotes_uses_the_pair_instrument() -> None:
    pair, quotes = _wrangled_fx_quotes()

    assert (quotes[0].instrument_id, quotes[1].instrument_id) == (pair.id, pair.id)


def test_wrangle_fx_quotes_builds_mid_prices() -> None:
    _pair, quotes = _wrangled_fx_quotes()

    assert (
        str(quotes[0].bid_price),
        str(quotes[0].ask_price),
        str(quotes[1].bid_price),
        str(quotes[1].ask_price),
    ) == ("1.08123", "1.08123", "1.08234", "1.08234")


def test_wrangle_fx_quotes_uses_precision_correct_default_sizes() -> None:
    _pair, quotes = _wrangled_fx_quotes()

    assert (
        str(quotes[0].bid_size),
        str(quotes[0].ask_size),
        quotes[0].bid_size.precision,
        quotes[0].ask_size.precision,
        str(quotes[1].bid_size),
        str(quotes[1].ask_size),
        quotes[1].bid_size.precision,
        quotes[1].ask_size.precision,
    ) == ("1000000", "1000000", 0, 0, "1000000", "1000000", 0, 0)


def test_wrangle_fx_quotes_preserves_event_and_init_timestamps() -> None:
    _pair, quotes = _wrangled_fx_quotes()

    assert (
        quotes[0].ts_event,
        quotes[0].ts_init,
        quotes[1].ts_event,
        quotes[1].ts_init,
    ) == (
        1_704_153_600_000_000_000,
        1_704_153_600_000_000_000,
        1_704_240_000_000_000_000,
        1_704_240_000_000_000_000,
    )


def _wrangled_fx_quotes() -> tuple[CurrencyPair, list[QuoteTick]]:
    pair = build_currency_pair("EUR", "USD", "IDEALPRO")
    rates = pd.Series(
        [1.08123, 1.08234],
        index=pd.to_datetime(["2024-01-02T00:00:00Z", "2024-01-03T00:00:00Z"]),
    )
    return pair, wrangle_fx_quotes(pair, rates)


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
