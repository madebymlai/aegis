"""Backtest data loading — the LOAD side of the data concern (ADR-0003).

``MarketDataPort`` is the runtime READ side over the reconciled cache; this is
its complement for backtests: it turns provider-agnostic OHLCV frames into the
Nautilus instruments and ``Bar`` objects a ``BacktestEngine`` consumes, built on
the kernel's own ``BarDataWrangler`` (the DataEngine ingestion path) rather than
hand-rolled bar loops.

An instrument is keyed ``FIGI.venue`` so it matches the overlay's FIGI->
InstrumentId bimap; OHLCV is a frame with ``open/high/low/close/volume`` columns
on a ``DatetimeIndex`` (whatever provider produced it — the loader never fetches).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.wranglers import BarDataWrangler


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


def daily_bar_type(instrument: Equity) -> BarType:
    """The 1-DAY LAST-EXTERNAL bar type the overlay subscribes for *instrument*."""
    return BarType.from_str(f"{instrument.id.value}-1-DAY-LAST-EXTERNAL")


def wrangle_daily_bars(instrument: Equity, ohlcv: pd.DataFrame) -> list[Bar]:
    """Wrangle an OHLCV frame into the instrument's daily ``Bar`` list."""
    wrangler = BarDataWrangler(daily_bar_type(instrument), instrument)
    return wrangler.process(ohlcv)
