"""E2E: a Book Config cap above its bundle's research-validated cap is rejected
at load (Wave B / B13).

The provenance check runs in ``on_start``; a violation halts the book, so the
backtest produces zero fills even though the bundle would otherwise trade.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, TraderId, Venue
from nautilus_trader.model.objects import Currency, Money
from conftest import eur_equity

from aegis_runtime import (
    ListedRef,
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
)

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.pipeline import FixtureInstrumentResolver
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

VENUE = Venue("XLON")
_FIGI = "BBG000B9XRY4"
_BUNDLE_GROSS_CAP = 1.0


class _FixedWeightBundle(ExecutionBundle):
    """Always allocates a fixed weight; gross_cap is the validated ceiling."""

    def __init__(self, figi: str, weight: float) -> None:
        self._figi = figi
        self._weight = weight
        contract = DataContract(
            refs=(ListedRef(figi),), required_arrays=("Close",), base_currency="EUR",
            required_fx_currencies=(), timeframe="1D", lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id=f"synth-{figi}", role="synth", candidate_key="k",
            component_source_hashes={}, refs=(ListedRef(figi),),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy", component_id="s", module="m",
                input_names=(), output_names=(), params={},
            ),
            indicators=(), gross_cap=_BUNDLE_GROSS_CAP, net_cap=None,
            direction="both", symbols=(figi,), currency_by_symbol={figi: "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices, *, fx_series=None):
        close = prices.array("Close")
        df = pd.DataFrame({self._figi: [self._weight] * len(close)}, index=close.index)
        df.columns.name = "figi"
        return df


def _make_bars(figi: str) -> list[Bar]:
    instrument = eur_equity(figi, VENUE.value)
    bar_type = BarType.from_str(f"{instrument.id.value}-1-DAY-LAST-EXTERNAL")
    interval = 86_400_000_000_000
    bars, ts = [], 0
    for px in [100.0, 101.0, 102.0, 103.0]:
        p = instrument.make_price(px)
        bars.append(Bar(bar_type=bar_type, open=p, high=p, low=p, close=p,
                        volume=instrument.make_qty(1000), ts_event=ts, ts_init=ts))
        ts += interval
    return bars


def test_cap_violating_book_is_rejected_at_load():
    """book.gross_cap (1.5) > bundle.gross_cap (1.0) → halted, zero fills."""
    book = BookConfig(
        sleeves=(SleeveConfig(name=SleeveName("trend"), wheel_filename="trend.whl", risk_share=1.0),),
        base_currency="EUR",
        gross_cap=_BUNDLE_GROSS_CAP + 0.5,  # looser than research validated
    )
    instr = eur_equity(_FIGI, VENUE.value)

    engine = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("CAP-E2E"), logging=None))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(instr)
    engine.add_data(_make_bars(_FIGI))

    strategy = RebalanceStrategy(config=RebalanceStrategyConfig(book=book))
    strategy.register_sleeve(book.sleeves[0].name, _FixedWeightBundle(_FIGI, 0.5))
    strategy.set_instrument_resolver(
        FixtureInstrumentResolver({ListedRef(_FIGI): InstrumentId.from_str(f"{_FIGI}.{VENUE.value}")})
    )
    engine.add_strategy(strategy)

    engine.run()

    assert strategy._is_halted is True
    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert len(fills) == 0, f"halted book must not trade, got {len(fills)} fills"

    engine.dispose()
