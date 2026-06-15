"""Integration tests for NautilusMarketData (Wave B / B11).

The data adapter hides the Strategy's ``cache.instrument(...)`` reads behind a
narrow MarketDataPort: per-instrument sizing metadata (currency + size
increment) and Nautilus quantity construction.  Tested against a fake
CacheFacade holding a real Equity, so quote_currency/size_increment/make_qty are
exercised for real; the full path is proven by the e2e BacktestEngine suite.
"""

from __future__ import annotations

from nautilus_trader.model.currencies import EUR
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity

from aegis_trader.data.nautilus import NautilusMarketData
from aegis_trader.domain.sizing import InstrumentSizing

_IID = InstrumentId(symbol=Symbol("VUSA"), venue=Venue("XLON"))


def _equity() -> Equity:
    return Equity(
        instrument_id=_IID,
        raw_symbol=Symbol("VUSA"),
        currency=EUR,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


class _FakeCache:
    def __init__(self, instruments: dict[InstrumentId, Equity]) -> None:
        self._instruments = instruments

    def instrument(self, instrument_id: InstrumentId):
        return self._instruments.get(instrument_id)


def test_instrument_sizing_reads_currency_and_increment():
    md = NautilusMarketData(cache=_FakeCache({_IID: _equity()}))

    sizing = md.instrument_sizing(_IID)

    assert sizing == InstrumentSizing(currency="EUR", size_increment=1.0)


def test_make_quantity_builds_a_venue_quantity():
    md = NautilusMarketData(cache=_FakeCache({_IID: _equity()}))

    qty = md.make_quantity(_IID, 22_000.0)

    assert isinstance(qty, Quantity)
    assert float(qty.as_double()) == 22_000.0


def test_instrument_sizing_none_when_not_cached():
    md = NautilusMarketData(cache=_FakeCache({}))
    assert md.instrument_sizing(_IID) is None


def test_make_quantity_none_when_not_cached():
    md = NautilusMarketData(cache=_FakeCache({}))
    assert md.make_quantity(_IID, 100.0) is None
