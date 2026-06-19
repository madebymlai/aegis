"""E2E: per-sleeve attribution runs on REAL per-period NAV (Wave B / B14).

The strategy records the book's actual NAV each rebalance period (via the
BookStatePort) and feeds that series into compute_sleeve_attribution, replacing
the old _ATTRIBUTION_PLACEHOLDER_NAV constant.  With a held position and moving
prices the real NAV varies period to period — impossible under a constant
placeholder — which is the observable signature of the fix.
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
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

VENUE = Venue("XLON")
_FIGI = "BBG000B9XRY4"


class _FixedWeightBundle(ExecutionBundle):
    def __init__(self, figi: str, weight: float) -> None:
        self._figi = figi
        self._weight = weight
        contract = DataContract(
            refs=(ListedRef(figi),), required_arrays=("Close",), base_currency="EUR",
            required_fx_currencies=(), timeframe="1D", lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="synth", role="synth", candidate_key="k",
            component_source_hashes={}, refs=(ListedRef(figi),),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy", component_id="s", module="m",
                input_names=(), output_names=(), params={},
            ),
            indicators=(), gross_cap=1.0, net_cap=None, direction="both",
            symbols=(figi,), currency_by_symbol={figi: "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices, *, fx_series=None):
        close = prices.array("Close")
        df = pd.DataFrame({self._figi: [self._weight] * len(close)}, index=close.index)
        df.columns.name = "figi"
        return df


def _make_bars(figi: str, prices: list[float]) -> list[Bar]:
    instrument = eur_equity(figi, VENUE.value)
    bar_type = BarType.from_str(f"{instrument.id.value}-1-DAY-LAST-EXTERNAL")
    interval = 86_400_000_000_000
    bars, ts = [], 0
    for px in prices:
        p = instrument.make_price(px)
        bars.append(Bar(bar_type=bar_type, open=p, high=p, low=p, close=p,
                        volume=instrument.make_qty(1000), ts_event=ts, ts_init=ts))
        ts += interval
    return bars


def test_attribution_uses_real_per_period_nav():
    book = BookConfig(
        sleeves=(SleeveConfig(name=SleeveName("trend"), wheel_filename="trend.whl", risk_share=1.0),),
        base_currency="EUR",
    )
    instr = eur_equity(_FIGI, VENUE.value)
    # Rising prices → the held position's unrealized P&L (and thus NAV) moves.
    bars = _make_bars(_FIGI, [100.0, 110.0, 120.0, 130.0, 140.0, 150.0])

    engine = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("ATTR-E2E"), logging=None))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(instr)
    engine.add_data(bars)

    strategy = RebalanceStrategy(config=RebalanceStrategyConfig(book=book))
    strategy.register_sleeve(book.sleeves[0].name, _FixedWeightBundle(_FIGI, 0.5))
    strategy._figi_bimap = {ListedRef(_FIGI): InstrumentId.from_str(f"{_FIGI}.{VENUE.value}")}
    engine.add_strategy(strategy)

    engine.run()

    # Real per-period NAV was recorded, and it moved (placeholder was constant).
    assert len(strategy._nav_history) >= 2
    assert len(set(strategy._nav_history)) > 1, (
        f"NAV should vary with the held position's P&L; got {strategy._nav_history}"
    )
    # Attribution ran on that real NAV.
    assert strategy._last_attribution

    engine.dispose()


def _left_skewed_prices() -> list[float]:
    """A price path whose returns are left-skewed: mostly small gains, occasional
    sharp drops — i.e. a net-concave realized return distribution (skew < 0)."""
    prices = [100.0]
    for _ in range(6):
        for _ in range(4):
            prices.append(prices[-1] * 1.01)
        prices.append(prices[-1] * 0.88)
    return prices


def test_realized_book_skew_is_recorded_as_evidence():
    """Observability replaces the deleted live skew solve (aegis-rd-ytr.2).

    Net-convexity is by construction, not enforced — so the book must *record*
    its realized skew, otherwise deleting the guard leaves it blind.  Here a
    left-skewed (net-concave) price path drives a negative realized book skew,
    and the strategy surfaces it as evidence rather than silently re-weighting.
    """
    book = BookConfig(
        sleeves=(SleeveConfig(name=SleeveName("trend"), wheel_filename="trend.whl", risk_share=1.0),),
        base_currency="EUR",
    )
    instr = eur_equity(_FIGI, VENUE.value)
    bars = _make_bars(_FIGI, _left_skewed_prices())

    engine = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("SKEW-E2E"), logging=None))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(instr)
    engine.add_data(bars)

    strategy = RebalanceStrategy(config=RebalanceStrategyConfig(book=book))
    strategy.register_sleeve(book.sleeves[0].name, _FixedWeightBundle(_FIGI, 0.5))
    strategy._figi_bimap = {ListedRef(_FIGI): InstrumentId.from_str(f"{_FIGI}.{VENUE.value}")}
    engine.add_strategy(strategy)

    engine.run()

    # Realized book skew was recorded (mandatory observability) and reflects the
    # net-concave path — the operator can see it, no live re-weighting happened.
    assert strategy._last_book_skew is not None
    assert strategy._last_book_skew < 0.0

    engine.dispose()
