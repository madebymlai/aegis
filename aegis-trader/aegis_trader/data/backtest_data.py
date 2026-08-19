"""Backtest-only instrument and synthetic FX quote helpers."""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.wranglers import QuoteTickDataWrangler

_FX_PRICE_PRECISION = 5
_FX_SIZE = 1_000_000


def build_currency_pair(
    base_currency: str, quote_currency: str, venue: str
) -> CurrencyPair:
    """A spot FX ``CurrencyPair`` (``base/quote``) on *venue*.

    Backtests feed FX the same way live does — as a quote-tick'd reference pair —
    so the overlay marks the cache xrate from it (``on_quote_tick``) and the
    accounting layer values foreign legs from the same quotes.
    """
    symbol = Symbol(f"{base_currency}/{quote_currency}")
    return CurrencyPair(
        instrument_id=InstrumentId(symbol=symbol, venue=Venue(venue)),
        raw_symbol=symbol,
        base_currency=Currency.from_str(base_currency),
        quote_currency=Currency.from_str(quote_currency),
        price_precision=_FX_PRICE_PRECISION,
        size_precision=0,
        price_increment=Price(10**-_FX_PRICE_PRECISION, _FX_PRICE_PRECISION),
        size_increment=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def wrangle_fx_quotes(pair: CurrencyPair, fx_series: pd.Series) -> list[QuoteTick]:
    """One ``bid == ask`` quote per date in *fx_series*, at that date's rate.

    The overlay marks the cache xrate from each quote (``on_quote_tick``) and the
    accounting layer values foreign legs from the same per-date quotes, so a
    backtest tracks historical FX instead of one flat rate across the window.
    """
    if fx_series.empty:
        return []
    quotes = pd.DataFrame(
        {
            "bid_price": fx_series,
            "ask_price": fx_series,
        }
    )
    return QuoteTickDataWrangler(pair).process(quotes, default_volume=_FX_SIZE)
