"""Backtest data loading helpers.

``MarketDataPort`` is the runtime READ side over the reconciled cache; this is
its complement for backtests: it turns catalog OHLCV frames into the ``Bar``
objects a ``BacktestEngine`` consumes, built on Nautilus'
``BarDataWrangler`` rather than hand-rolled bar loops.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import Bar, QuoteTick
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair, Instrument
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.wranglers import BarDataWrangler, QuoteTickDataWrangler

from aegis_data.marking import DeclaredMarkingResolver, RawBarTypeResolver

_FX_PRICE_PRECISION = 5
_FX_SIZE = 1_000_000


def wrangle_bars(
    instrument: Instrument,
    ohlcv: pd.DataFrame,
    timeframe: str,
    *,
    resolver: RawBarTypeResolver = DeclaredMarkingResolver(),
) -> list[Bar]:
    """Wrangle an OHLCV frame into the instrument's ``Bar`` list at *timeframe*.

    The bar identity comes from the injected marking *resolver* (the one raw
    bar-type resolution seam) — a bar-marked instrument wrangles onto its single
    mark bar (LAST, or MID for cash FX)."""
    marking = resolver.resolve(instrument.id, timeframe)
    wrangler = BarDataWrangler(marking.mark_bars[0], instrument)
    return wrangler.process(ohlcv)


def wrangle_quote_bars(
    instrument: Instrument,
    bid_ohlcv: pd.DataFrame,
    ask_ohlcv: pd.DataFrame,
    timeframe: str,
    *,
    resolver: RawBarTypeResolver,
) -> list[Bar]:
    """Wrangle a quote-marked instrument's sided frames into BID + ASK ``Bar``\\ s.

    The simulated venue pairs same-timestamp BID/ASK EXTERNAL bars into L1
    quote updates, so these two series alone drive the book: fills execute at
    the real touch and no MID bar ever reaches the venue (aegis-rd-tggo.5).
    """
    bid_type, ask_type = resolver.resolve(instrument.id, timeframe).mark_bars
    return [
        *BarDataWrangler(bid_type, instrument).process(bid_ohlcv),
        *BarDataWrangler(ask_type, instrument).process(ask_ohlcv),
    ]


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
