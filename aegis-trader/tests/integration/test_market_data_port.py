"""Integration tests for NautilusMarketData (Wave B / B11).

The data adapter hides the Strategy's ``cache.instrument(...)`` reads behind a
narrow MarketDataPort: per-instrument sizing metadata (currency + size
increment) and Nautilus quantity construction.  Tested against a fake
CacheFacade holding a real Equity, so quote_currency/size_increment/make_qty are
exercised for real; the full path is proven by the e2e BacktestEngine suite.
"""

from __future__ import annotations

from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.currencies import EUR
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity
from aegis_trader.data import NautilusMarketData, raw_bar_type
from aegis_trader.domain.sizing import InstrumentSizing

_IID = InstrumentId(symbol=Symbol("VUSA"), venue=Venue("XLON"))
_DAY_NS = 86_400_000_000_000


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


def test_lookback_window_reads_completed_bars_from_cache_without_trigger_bar():
    cache = Cache()
    bar_type_ = raw_bar_type(_IID, "1D")
    cache.add_bars(
        [
            _bar(bar_type_, 0, 100.0),
            _bar(bar_type_, _DAY_NS, 101.0),
            _bar(bar_type_, 2 * _DAY_NS, 102.0),
        ]
    )
    md = NautilusMarketData(cache=cache)

    bars = md.lookback_window(
        _IID,
        "1D",
        period=1,
        period_ns=_DAY_NS,
        limit=2,
    )

    assert [bar.close for bar in bars] == [100.0, 101.0]


def test_freshness_true_when_cache_has_bar_in_completed_period():
    cache = Cache()
    bar_type_ = raw_bar_type(_IID, "1D")
    cache.add_bars([_bar(bar_type_, _DAY_NS, 101.0)])
    md = NautilusMarketData(cache=cache)

    fresh = md.has_bar_in_period(
        _IID,
        "1D",
        period=1,
        period_ns=_DAY_NS,
    )

    assert fresh is True


def test_freshness_false_when_cache_has_no_bar_in_completed_period():
    cache = Cache()
    bar_type_ = raw_bar_type(_IID, "1D")
    cache.add_bars([_bar(bar_type_, 0, 100.0), _bar(bar_type_, 2 * _DAY_NS, 102.0)])
    md = NautilusMarketData(cache=cache)

    fresh = md.has_bar_in_period(
        _IID,
        "1D",
        period=1,
        period_ns=_DAY_NS,
    )

    assert fresh is False


def _bar(bar_type_, ts_event: int, close: float) -> Bar:
    price = Price.from_str(f"{close:.2f}")
    return Bar(
        bar_type=bar_type_,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Quantity.from_int(1_000),
        ts_event=ts_event,
        ts_init=ts_event,
    )
