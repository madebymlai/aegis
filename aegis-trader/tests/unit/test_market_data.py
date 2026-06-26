"""Unit tests for NautilusMarketData — the MarketDataPort adapter (Wave C FX).

FX rates are sourced from the Nautilus Cache's *mark xrate* (settable in tests
and live, venue-decoupled, auto-inverting), returning None when unavailable so
the overlay fails closed rather than fabricating a rate.
"""

import pandas as pd
import pytest
from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.currencies import EUR, GBP, USD
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Equity, FuturesContract
from nautilus_trader.model.objects import Price, Quantity

from aegis_trader.data.bar_type import raw_bar_type
from aegis_trader.data.market_data import NautilusMarketData

_DAY_NS = 86_400_000_000_000


class TestFxRate:
    def test_fx_rate_base_to_quote(self):
        """fx_rate(base, quote) returns quote units per 1 base (EUR→GBP)."""
        cache = Cache()
        cache.set_mark_xrate(EUR, GBP, 0.85)  # 0.85 GBP per 1 EUR
        md = NautilusMarketData(cache=cache)
        assert md.fx_rate("EUR", "GBP") == pytest.approx(0.85)

    def test_fx_rate_inverse_available(self):
        cache = Cache()
        cache.set_mark_xrate(EUR, GBP, 0.85)
        md = NautilusMarketData(cache=cache)
        assert md.fx_rate("GBP", "EUR") == pytest.approx(1.0 / 0.85)

    def test_fx_rate_unset_returns_none(self):
        """No rate in the cache → None (caller fails closed, never fabricates)."""
        md = NautilusMarketData(cache=Cache())
        assert md.fx_rate("EUR", "GBP") is None

    def test_fx_rate_same_currency_is_one(self):
        md = NautilusMarketData(cache=Cache())
        assert md.fx_rate("EUR", "EUR") == pytest.approx(1.0)


class _StubFeed:
    """A ContinuousFeed stand-in: continuous_id + series() (the signal data) + front_contract()
    (the real tradeable leg that sizing/execution resolve to)."""

    def __init__(
        self,
        continuous_id: InstrumentId,
        frame: pd.DataFrame,
        front: InstrumentId | None = None,
    ) -> None:
        self.continuous_id = continuous_id
        self._frame = frame
        self._front = front if front is not None else continuous_id

    def series(self) -> pd.DataFrame:
        return self._frame

    def front_contract(self) -> InstrumentId:
        return self._front


def _equity(instrument_id: InstrumentId) -> Equity:
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=instrument_id.symbol,
        currency=EUR,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def _future(instrument_id: InstrumentId, *, multiplier: int) -> FuturesContract:
    return FuturesContract(
        instrument_id=instrument_id,
        raw_symbol=instrument_id.symbol,
        asset_class=AssetClass.INDEX,
        exchange=instrument_id.venue.value,
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.25"),
        multiplier=Quantity.from_int(multiplier),
        lot_size=Quantity.from_int(1),
        underlying="ES",
        activation_ns=0,
        expiration_ns=pd.Timestamp("2024-03-15", tz="UTC").value,
        ts_event=0,
        ts_init=0,
    )


def _ohlcv_frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.to_datetime([i * _DAY_NS for i in range(len(closes))])  # tz-naive, one bar per day
    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": closes},
        index=idx,
    )


def _bar(bar_type: object, ts: int, close: float) -> Bar:
    price = Price.from_str(str(close))
    return Bar(bar_type, price, price, price, price, Quantity.from_int(1), ts, ts)


class TestContinuousReads:
    def test_lookback_window_reads_a_continuous_root_from_the_feed(self):
        """A continuous root is read from the feed's re-based series (not the cache), still
        honouring the one-bar-lag/no-look-ahead contract: the trigger bar at the period edge
        is excluded."""
        es = InstrumentId.from_str("ES.XCME")
        md = NautilusMarketData(cache=Cache(), feeds=(_StubFeed(es, _ohlcv_frame([100.0, 101.0, 102.0])),))

        bars = md.lookback_window(es, "1D", period=1, period_ns=_DAY_NS, limit=2)

        assert [bar.close for bar in bars] == [100.0, 101.0]
        assert bars[0].ts_event == 0

    def test_raw_instruments_still_read_from_the_cache_when_a_feed_is_present(self):
        """A feed for a continuous root does not divert raw-instrument reads — those stay on the
        cache via the raw bar type."""
        es = InstrumentId.from_str("ES.XCME")
        raw_id = InstrumentId.from_str("AAPL.NASDAQ")
        cache = Cache()
        bar_type_ = raw_bar_type(raw_id, "1D")
        cache.add_bars(
            [_bar(bar_type_, 0, 100.0), _bar(bar_type_, _DAY_NS, 101.0), _bar(bar_type_, 2 * _DAY_NS, 102.0)]
        )
        md = NautilusMarketData(cache=cache, feeds=(_StubFeed(es, _ohlcv_frame([1.0, 2.0, 3.0])),))

        bars = md.lookback_window(raw_id, "1D", period=1, period_ns=_DAY_NS, limit=2)

        assert [bar.close for bar in bars] == [100.0, 101.0]

    def test_has_bar_in_period_reads_the_feed_for_a_continuous_root(self):
        es = InstrumentId.from_str("ES.XCME")
        md = NautilusMarketData(cache=Cache(), feeds=(_StubFeed(es, _ohlcv_frame([100.0, 101.0])),))

        assert md.has_bar_in_period(es, "1D", period=1, period_ns=_DAY_NS)
        assert not md.has_bar_in_period(es, "1D", period=5, period_ns=_DAY_NS)

    def test_instrument_sizing_for_a_continuous_root_resolves_to_the_front_leg(self):
        """A continuous root is synthetic — its sizing metadata comes from the real front leg the
        order will trade (the cache holds the leg, never the synthetic root)."""
        es = InstrumentId.from_str("ES.XCME")
        front = InstrumentId.from_str("ESM4.XCME")
        cache = Cache()
        cache.add_instrument(_equity(front))
        md = NautilusMarketData(cache=cache, feeds=(_StubFeed(es, _ohlcv_frame([100.0]), front),))

        assert md.instrument_sizing(es) == md.instrument_sizing(front)
        assert md.instrument_sizing(es) is not None

    def test_instrument_sizing_carries_the_futures_contract_multiplier(self):
        """A futures front leg's sizing metadata must carry its contract multiplier (ES ×50),
        not silently drop it — dropping it over-sizes the order by the multiplier."""
        es = InstrumentId.from_str("ES.XCME")
        front = InstrumentId.from_str("ESH4.XCME")
        cache = Cache()
        cache.add_instrument(_future(front, multiplier=50))
        md = NautilusMarketData(cache=cache, feeds=(_StubFeed(es, _ohlcv_frame([100.0]), front),))

        sizing = md.instrument_sizing(es)

        assert sizing is not None
        assert sizing.multiplier == pytest.approx(50.0)

    def test_make_quantity_for_a_continuous_root_builds_a_front_leg_quantity(self):
        es = InstrumentId.from_str("ES.XCME")
        front = InstrumentId.from_str("ESM4.XCME")
        cache = Cache()
        cache.add_instrument(_equity(front))
        md = NautilusMarketData(cache=cache, feeds=(_StubFeed(es, _ohlcv_frame([100.0]), front),))

        qty = md.make_quantity(es, 7.0)

        assert isinstance(qty, Quantity)
        assert float(qty.as_double()) == 7.0

    def test_execution_instrument_id_routes_continuous_root_and_passes_native_through(self):
        """A continuous root resolves to its front leg; a native id passes through unchanged even
        when feeds are present — the regression guard that the equity/native path is untouched."""
        es = InstrumentId.from_str("ES.XCME")
        front = InstrumentId.from_str("ESM4.XCME")
        native = InstrumentId.from_str("VUSA.XLON")
        md = NautilusMarketData(cache=Cache(), feeds=(_StubFeed(es, _ohlcv_frame([100.0]), front),))

        assert md.execution_instrument_id(es) == front
        assert md.execution_instrument_id(native) == native
