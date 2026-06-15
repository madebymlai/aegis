"""E2E for Wave C (aegis-rd-bwb.3): real cross-currency FX sizing.

A GBP-denominated instrument trades against an EUR book.  The overlay sources a
live GBP/EUR rate from the Cache's mark xrate (set here; in live it arrives from
the venue), converts the EUR notional to GBP shares, and sizes correctly.  No
rate → the overlay fails closed (no fabricated FX, no order).
"""

from __future__ import annotations

import pandas as pd
import pytest
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.currencies import EUR, GBP
from nautilus_trader.model.data import Bar, BarType, QuoteTick
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue
from nautilus_trader.model.instruments import CurrencyPair, Instrument
from nautilus_trader.model.objects import Money, Price, Quantity

from conftest import gbp_equity

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
)

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_FIGI = "BBG000C6K6G9"  # a London-listed name (GBP)
VENUE = Venue("XLON")
_EURGBP = 0.85  # 0.85 GBP per 1 EUR


class _GbpBundle(ExecutionBundle):
    """Constant-weight bundle for a single GBP instrument (no bundle-level FX:
    required_fx_currencies=() — this isolates the *sizing* FX path)."""

    def __init__(self, weight: float = 0.5) -> None:
        self._weight = weight
        contract = DataContract(
            figis=(_FIGI,), required_arrays=("Close",), base_currency="EUR",
            required_fx_currencies=(), timeframe="1D", lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="fx-001", role="synth", candidate_key="k",
            component_source_hashes={}, figis=(_FIGI,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(family="strategy", component_id="s", module="m",
                                   input_names=(), output_names=(), params={}),
            indicators=(), gross_cap=1.0, net_cap=None, direction="both",
            symbols=(_FIGI,), currency_by_symbol={_FIGI: "GBP"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle, *, fx_series=None) -> pd.DataFrame:
        close = prices.array("Close")
        df = pd.DataFrame({_FIGI: [self._weight] * len(close)}, index=close.index)
        df.columns.name = "figi"
        return df


def _make_instrument() -> Instrument:
    return gbp_equity(_FIGI, VENUE.value)


def _make_bars(prices: list[float]) -> list[Bar]:
    instrument = _make_instrument()
    bar_type = BarType.from_str(f"{instrument.id.value}-1-DAY-LAST-EXTERNAL")
    interval_ns = 86_400_000_000_000
    bars: list[Bar] = []
    ts = 0
    for px in prices:
        p = instrument.make_price(px)
        bars.append(Bar(
            bar_type=bar_type, open=p, high=p, low=p, close=p,
            volume=instrument.make_qty(1000), ts_event=ts, ts_init=ts,
        ))
        ts += interval_ns
    return bars


def _make_book() -> BookConfig:
    return BookConfig(
        sleeves=(SleeveConfig(name=SleeveName("uk"), wheel_filename="uk.whl", risk_share=1.0),),
        base_currency="EUR",
    )


def _build_engine() -> BacktestEngine:
    engine = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("FX-E2E"), logging=None))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
        base_currency=EUR,
        starting_balances=[Money(100_000, EUR)],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(_make_instrument())
    # Live GBP/EUR rate (in live it arrives from the venue's quotes).
    engine.cache.set_mark_xrate(EUR, GBP, _EURGBP)
    return engine


def test_gbp_instrument_sizes_with_live_fx():
    """A GBP instrument sizes to the correct GBP share count via the FX rate.

    weight 0.5 × NAV 100_000 EUR = 50_000 EUR; × 0.85 GBP/EUR = 42_500 GBP;
    / price 85 GBP = 500 shares.
    """
    engine = _build_engine()
    engine.add_data(_make_bars([85.0, 85.0, 85.0, 85.0, 85.0]))  # flat GBP price

    book = _make_book()
    strategy = RebalanceStrategy(config=RebalanceStrategyConfig(book=book))
    strategy.register_sleeve(book.sleeves[0].name, _GbpBundle(0.5))
    strategy._figi_bimap = {_FIGI: InstrumentId.from_str(f"{_FIGI}.{VENUE.value}")}
    engine.add_strategy(strategy)

    engine.run()

    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert len(fills) >= 1, "Expected the GBP instrument to be sized and traded"
    for f in fills:
        assert f.is_buy
        assert float(f.quantity.as_double()) == pytest.approx(500.0, rel=1e-2)

    engine.dispose()


class _FxRequiringBundle(ExecutionBundle):
    """Bundle that DECLARES it needs a GBP→base FX series and records what it
    is handed, so we can assert the overlay supplies it from live data."""

    def __init__(self, weight: float = 0.5) -> None:
        self._weight = weight
        self.received_fx_series: dict | None = "UNCALLED"  # type: ignore[assignment]
        contract = DataContract(
            figis=(_FIGI,), required_arrays=("Close",), base_currency="EUR",
            required_fx_currencies=("GBP",), timeframe="1D", lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="fx-002", role="synth", candidate_key="k",
            component_source_hashes={}, figis=(_FIGI,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(family="strategy", component_id="s", module="m",
                                   input_names=(), output_names=(), params={}),
            indicators=(), gross_cap=1.0, net_cap=None, direction="both",
            symbols=(_FIGI,), currency_by_symbol={_FIGI: "GBP"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle, *, fx_series=None) -> pd.DataFrame:
        self.received_fx_series = fx_series
        close = prices.array("Close")
        df = pd.DataFrame({_FIGI: [self._weight] * len(close)}, index=close.index)
        df.columns.name = "figi"
        return df


def _run_with_bundle(bundle: ExecutionBundle, *, set_fx: bool) -> tuple[BacktestEngine, list]:
    engine = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("FX-REQ-E2E"), logging=None))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
        base_currency=EUR, starting_balances=[Money(100_000, EUR)], book_type=BookType.L1_MBP,
    )
    engine.add_instrument(_make_instrument())
    if set_fx:
        engine.cache.set_mark_xrate(EUR, GBP, _EURGBP)
    engine.add_data(_make_bars([85.0, 85.0, 85.0, 85.0, 85.0]))
    book = _make_book()
    strategy = RebalanceStrategy(config=RebalanceStrategyConfig(book=book))
    strategy.register_sleeve(book.sleeves[0].name, bundle)
    strategy._figi_bimap = {_FIGI: InstrumentId.from_str(f"{_FIGI}.{VENUE.value}")}
    engine.add_strategy(strategy)
    engine.run()
    fills = [o for o in engine.cache.orders() if o.is_closed]
    return engine, fills


def test_required_fx_series_supplied_from_live_data():
    """A bundle's required_fx_currencies is satisfied from the live FX rate."""
    bundle = _FxRequiringBundle(0.5)
    engine, fills = _run_with_bundle(bundle, set_fx=True)
    assert isinstance(bundle.received_fx_series, dict)
    assert set(bundle.received_fx_series) == {"GBP"}
    assert float(bundle.received_fx_series["GBP"].iloc[-1]) == pytest.approx(_EURGBP)
    assert len(fills) >= 1
    engine.dispose()


def test_missing_required_fx_fails_closed():
    """No FX rate for a required currency → the sleeve is skipped, nothing trades
    (no fabricated rate, no order)."""
    bundle = _FxRequiringBundle(0.5)
    engine, fills = _run_with_bundle(bundle, set_fx=False)
    assert fills == [], "Expected no fills when a required FX rate is unavailable"
    assert bundle.received_fx_series == "UNCALLED", (
        "compute_weights must not run without its required FX series"
    )
    engine.dispose()


# -- valuing a held non-base position back to base (the realized-weight path) ----
#
# realized_weights values each held position in base via the SAME venue-agnostic
# mark xrate the sizer uses (cache.get_mark_xrate) — not a venue-scoped FX
# instrument.  This is what lets a non-base sleeve appear in the realized book
# (and therefore be rebalanced against, not re-bought as if flat) on any venue,
# without a per-venue FX CurrencyPair.

from aegis_trader.portfolio.book_state import NautilusBookState  # noqa: E402


def test_held_gbp_position_surfaces_in_realized_weights_via_mark_xrate():
    """A held GBP position is valued back to EUR via the mark xrate and surfaces
    in realized_weights at ~its target weight — the same rate the sizer used.

    weight 0.5 × NAV 100_000 EUR = 50_000 EUR → 500 shares × 85 GBP = 42_500 GBP
    held; ÷ 0.85 GBP/EUR ≈ 50_000 EUR exposure → ~0.5 of NAV.
    """
    engine = _build_engine()  # XLON, EUR account, mark xrate set, NO CurrencyPair
    engine.add_data(_make_bars([85.0, 85.0, 85.0, 85.0, 85.0]))
    book = _make_book()
    strategy = RebalanceStrategy(config=RebalanceStrategyConfig(book=book))
    strategy.register_sleeve(book.sleeves[0].name, _GbpBundle(0.5))
    strategy._figi_bimap = {_FIGI: InstrumentId.from_str(f"{_FIGI}.{VENUE.value}")}
    engine.add_strategy(strategy)
    engine.run()

    gbp_id = engine.cache.positions_open()[0].instrument_id
    book_state = NautilusBookState(
        portfolio=engine.portfolio, cache=engine.cache,
        base_currency=EUR, instr_to_figi={gbp_id.value: _FIGI},
    )

    weights = book_state.realized_weights()
    assert _FIGI in weights, "The held GBP sleeve must surface in realized_weights"
    assert weights[_FIGI] == pytest.approx(0.5, rel=5e-2)
    engine.dispose()


# -- the FX feed: marks maintained from live FX quotes (no manual set_mark_xrate) -
#
# In live the venue streams FX CurrencyPair quotes; the overlay turns them into
# the cache mark xrate that BOTH the sizer and realized_weights read.  This is
# the mechanism that replaces the backtest's manual set_mark_xrate in paper/live.

def _fx_pair_eurgbp() -> CurrencyPair:
    """EUR/GBP reference pair (price = GBP per 1 EUR)."""
    symbol = Symbol("EUR/GBP")
    return CurrencyPair(
        instrument_id=InstrumentId(symbol=symbol, venue=VENUE), raw_symbol=symbol,
        base_currency=EUR, quote_currency=GBP, price_precision=5, size_precision=0,
        price_increment=Price.from_str("0.00001"), size_increment=Quantity.from_int(1),
        lot_size=None, max_quantity=None, min_quantity=None, max_notional=None,
        min_notional=None, max_price=None, min_price=None, margin_init=0,
        margin_maint=0, maker_fee=0, taker_fee=0, ts_event=0, ts_init=0,
    )


def _fx_quotes(pair: CurrencyPair, rate: float, n: int = 5) -> list[QuoteTick]:
    """A flat top-of-book quote series carrying *rate* (quote per 1 base)."""
    p = pair.make_price(rate)
    interval, ts, out = 86_400_000_000_000, 0, []
    for _ in range(n):
        out.append(QuoteTick(
            instrument_id=pair.id, bid_price=p, ask_price=p,
            bid_size=Quantity.from_int(1_000_000), ask_size=Quantity.from_int(1_000_000),
            ts_event=ts, ts_init=ts,
        ))
        ts += interval
    return out


def test_overlay_marks_fx_from_quotes_so_non_base_sleeve_trades_and_surfaces():
    """With FX quotes flowing (and NO manual set_mark_xrate), the overlay marks
    the cache from them, so the GBP sleeve both sizes/fills (sizer reads the mark)
    and surfaces in realized_weights (valuation reads the same mark)."""
    engine = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("FX-FEED-E2E"), logging=None))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
        base_currency=EUR, starting_balances=[Money(100_000, EUR)], book_type=BookType.L1_MBP,
    )
    engine.add_instrument(_make_instrument())  # GBP equity
    fx = _fx_pair_eurgbp()
    engine.add_instrument(fx)
    engine.add_data(_fx_quotes(fx, _EURGBP))   # the FX feed — NO set_mark_xrate
    engine.add_data(_make_bars([85.0, 85.0, 85.0, 85.0, 85.0]))

    book = _make_book()
    strategy = RebalanceStrategy(config=RebalanceStrategyConfig(book=book))
    strategy.register_sleeve(book.sleeves[0].name, _GbpBundle(0.5))
    strategy._figi_bimap = {_FIGI: InstrumentId.from_str(f"{_FIGI}.{VENUE.value}")}
    engine.add_strategy(strategy)
    engine.run()

    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert fills, "FX-quote-derived mark must let the GBP sleeve size and fill"

    gbp_id = engine.cache.positions_open()[0].instrument_id
    book_state = NautilusBookState(
        portfolio=engine.portfolio, cache=engine.cache,
        base_currency=EUR, instr_to_figi={gbp_id.value: _FIGI},
    )
    assert _FIGI in book_state.realized_weights(), (
        "The GBP sleeve must surface in realized_weights from the FX-quote-derived mark"
    )
    engine.dispose()
