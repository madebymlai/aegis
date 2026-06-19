"""Backtest data loading — the LOAD side of the data concern (ADR-0003).

``MarketDataPort`` is the runtime READ side over the reconciled cache; this is
its complement for backtests: it turns Store Read OHLCV frames into the
Nautilus instruments and ``Bar`` objects a ``BacktestEngine`` consumes, built on
the kernel's own ``BarDataWrangler`` (the DataEngine ingestion path) rather than
hand-rolled bar loops.

An instrument is keyed ``FIGI.venue`` so it matches the overlay's FIGI->
InstrumentId bimap; OHLCV is a frame with ``open/high/low/close/volume`` columns
on a ``DatetimeIndex``. The loader adapts frames only; it never reads history.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from nautilus_trader.model.data import Bar, QuoteTick
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair, Equity
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.wranglers import BarDataWrangler

from aegis_trader.data.bar_type import bar_type

_FX_PRICE_PRECISION = 5
_FX_SIZE = 1_000_000


@dataclass(frozen=True)
class InstrumentSpec:
    """How to build one backtest instrument from a bundle's identity.

    ``figi``/``venue`` form the ``InstrumentId`` the overlay's bimap resolves to;
    ``quote_currency`` is the instrument's native quote token (the overlay
    converts to the book's base via FX).
    """

    figi: str
    venue: str
    quote_currency: str
    price_increment: str = "0.01"
    size_increment: int = 1


def build_equity(spec: InstrumentSpec) -> Equity:
    """A Nautilus ``Equity`` keyed ``FIGI.venue`` in its native quote currency."""
    increment = Price.from_str(spec.price_increment)
    return Equity(
        instrument_id=InstrumentId(symbol=Symbol(spec.figi), venue=Venue(spec.venue)),
        raw_symbol=Symbol(spec.figi),
        currency=Currency.from_str(spec.quote_currency),
        price_precision=abs(increment.precision),
        price_increment=increment,
        lot_size=Quantity.from_int(spec.size_increment),
        ts_event=0,
        ts_init=0,
    )


def wrangle_bars(instrument: Equity, ohlcv: pd.DataFrame, timeframe: str) -> list[Bar]:
    """Wrangle an OHLCV frame into the instrument's ``Bar`` list at *timeframe*
    (the contract timeframe; the LAST-EXTERNAL bar type is derived from it)."""
    wrangler = BarDataWrangler(bar_type(instrument.id.value, timeframe), instrument)
    return wrangler.process(ohlcv)


def build_currency_pair(base_currency: str, quote_currency: str, venue: str) -> CurrencyPair:
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
        price_increment=Price(10 ** -_FX_PRICE_PRECISION, _FX_PRICE_PRECISION),
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
    precision = pair.price_precision
    size = Quantity.from_int(_FX_SIZE)
    return [
        QuoteTick(
            instrument_id=pair.id,
            bid_price=Price(float(rate), precision),
            ask_price=Price(float(rate), precision),
            bid_size=size,
            ask_size=size,
            ts_event=ts.value,
            ts_init=ts.value,
        )
        for ts, rate in fx_series.items()
    ]
