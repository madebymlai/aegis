"""E2E for A7 part 2 (aegis-rd-bwb.1): the realized-book gate engages live.

Wiring ``realized_weights`` from the reconciled Cache means the overlay trades
the *drift* to target, not the full target every period: once a position is at
target it is HELD (within band), rather than re-bought each bar.

Setup: one sleeve, constant target weight 0.5, FLAT prices, so realized lands
exactly on target after the first fill — the band then suppresses all further
trades.  Before the wiring the strategy re-bought every period (multiple fills);
after, there is exactly one.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, TraderId, Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Currency, Money

from conftest import eur_equity

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

_FIGI = "BBG000B9XRY4"
VENUE = Venue("XLON")


class _FixedWeightBundle(ExecutionBundle):
    def __init__(self, weight: float = 0.5) -> None:
        self._weight = weight
        contract = DataContract(
            figis=(_FIGI,), required_arrays=("Close",), base_currency="EUR",
            required_fx_currencies=(), timeframe="1D", lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="rg-001", role="synth", candidate_key="k",
            component_source_hashes={}, figis=(_FIGI,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(family="strategy", component_id="s", module="m",
                                   input_names=(), output_names=(), params={}),
            indicators=(), gross_cap=1.0, net_cap=None, direction="both",
            symbols=(_FIGI,), currency_by_symbol={_FIGI: "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle, *, fx_series=None) -> pd.DataFrame:
        close = prices.array("Close")
        df = pd.DataFrame({_FIGI: [self._weight] * len(close)}, index=close.index)
        df.columns.name = "figi"
        return df


def _make_instrument() -> Instrument:
    return eur_equity(_FIGI, VENUE.value)


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
        sleeves=(SleeveConfig(name=SleeveName("tracer"), wheel_filename="t.whl", budget=1.0),),
        base_currency="EUR",
    )


def test_realized_gate_holds_after_reaching_target():
    """With realized-weight wiring, the overlay buys to target once then holds."""
    book = _make_book()
    bars = _make_bars([100.0, 100.0, 100.0, 100.0, 100.0])  # flat → realized == target

    engine = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("RG-E2E"), logging=None))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.CASH,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(_make_instrument())
    engine.add_data(bars)

    strategy = RebalanceStrategy(config=RebalanceStrategyConfig(book=book))
    strategy.register_sleeve(book.sleeves[0].name, _FixedWeightBundle(0.5))
    strategy._figi_bimap = {_FIGI: InstrumentId.from_str(f"{_FIGI}.{VENUE.value}")}
    engine.add_strategy(strategy)

    engine.run()

    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert len(fills) == 1, (
        f"Expected exactly 1 fill (buy to target, then hold), got {len(fills)}: "
        f"{[(f.side, float(f.quantity.as_double())) for f in fills]}"
    )
    assert fills[0].is_buy

    engine.dispose()
