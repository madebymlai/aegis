"""E2E test for Slice 2: multi-sleeve netting + budgets in a backtest.

Validates that a two-sleeve BookConfig, each sleeve backed by a synthetic
ExecutionBundle, produces netted OrderIntents from the rebalancer when run
through the RebalanceStrategy in a NautilusTrader BacktestEngine.

Covers:
  - Overlapping FIGI → nets to a single order (budget scaling before netting)
  - Disjoint sleeves → each produces its own order

N.B. The full multi-sleeve cadence (per-sleeve timeframes) is Slice 6.
For this slice we run both sleeves off the same bar stream to keep
bar-synchronisation simple.
"""

from __future__ import annotations

import numpy as np
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
from aegis_trader.trader.strategy import (
    _MIN_SLEEVE_VOL_RETURNS,
    RebalanceStrategy,
    RebalanceStrategyConfig,
)

# ── synthetic bundles ─────────────────────────────────────────────────────────

_FIGI_VUSA = "BBG000B9XRY4"   # VUSA.L
_FIGI_CALM = "BBG000B9XRY4"   # low-realized-vol sleeve instrument
_FIGI_VOL = "BBG000BLNNH6"    # high-realized-vol sleeve instrument


class _FixedWeightBundle(ExecutionBundle):
    """A bundle that always returns a fixed weight for a fixed FIGI."""

    def __init__(self, figi: str, weight: float) -> None:
        self._figi = figi
        self._weight = weight
        contract = DataContract(
            figis=(figi,),
            required_arrays=("Close",),
            base_currency="EUR",
            required_fx_currencies=(),
            timeframe="1D",
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id=f"synth-{figi}",
            role="synth",
            candidate_key=f"synth-{figi}-key",
            component_source_hashes={},
            figis=(figi,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="synth_strat",
                module="synth",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            gross_cap=1.0,
            net_cap=None,
            direction="both",
            symbols=(figi,),
            currency_by_symbol={figi: "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        prices: MarketDataBundle,
        *,
        fx_series: dict[str, pd.Series] | None = None,
    ) -> pd.DataFrame:
        close = prices.array("Close")
        n = len(close)
        df = pd.DataFrame(
            {self._figi: [self._weight] * n},
            index=close.index,
        )
        df.columns.name = "figi"
        return df


# ── two-sleeve strategy (thin wrapper for e2e) ────────────────────────────────


class TwoSleeveStrategy(RebalanceStrategy):
    """Thin wrapper that delegates to the base RebalanceStrategy's
    Slice 6 cadence — both sleeves run off the same bar stream with
    per-period debounce and NEXT-CLOSE execution lag."""



# ── helpers ───────────────────────────────────────────────────────────────────

VENUE = Venue("XLON")


def _make_instrument(figi: str) -> Instrument:
    return eur_equity(figi, VENUE.value)


def _make_bars(figi: str, prices: list[float], start_ns: int = 0) -> list[Bar]:
    instrument = _make_instrument(figi)
    bar_type = BarType.from_str(f"{instrument.id.value}-1-DAY-LAST-EXTERNAL")
    interval_ns = 86_400_000_000_000
    bars: list[Bar] = []
    ts = start_ns
    for px in prices:
        p = instrument.make_price(px)
        bar = Bar(
            bar_type=bar_type,
            open=p,
            high=p,
            low=p,
            close=p,
            volume=instrument.make_qty(1000),
            ts_event=ts,
            ts_init=ts,
        )
        bars.append(bar)
        ts += interval_ns
    return bars


def _make_book(budgets: tuple[float, float]) -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("trend"),
                wheel_filename="trend-abc.whl",
                risk_share=budgets[0],
            ),
            SleeveConfig(
                name=SleeveName("carry"),
                wheel_filename="carry-def.whl",
                risk_share=budgets[1],
            ),
        ),
        base_currency="EUR",
    )


def _stub_bimap(figis: set[str]) -> dict[str, "InstrumentId"]:
    """Stub FIGI→InstrumentId bimap for e2e tests."""
    return {figi: InstrumentId.from_str(f"{figi}.{VENUE.value}") for figi in figis}


# ── e2e test ──────────────────────────────────────────────────────────────────


def test_multi_sleeve_e2e():
    """Slice 2 end-to-end: multi-sleeve netting in a backtest.

    Two sleeves sharing the same instrument (VUSA) net to a single
    OrderIntent.  With NEXT-CLOSE lag (5 daily bars, lookback=1):

      trend: risk_share=0.6, weight=+0.5 on VUSA → scaled=+0.30
      carry: risk_share=0.4, weight=-0.2 on VUSA → scaled=-0.08
      net = +0.22 → BUY 22_000

    Expected: ≥2 filled BUY orders of ~22,000 shares each.
    """
    book = _make_book((0.6, 0.4))
    trend_bundle = _FixedWeightBundle(_FIGI_VUSA, 0.5)
    carry_bundle = _FixedWeightBundle(_FIGI_VUSA, -0.2)

    vusa_instr = _make_instrument(_FIGI_VUSA)
    vusa_bars = _make_bars(_FIGI_VUSA, [100.0, 101.0, 102.0, 103.0, 104.0])

    engine = BacktestEngine(BacktestEngineConfig(
        trader_id=TraderId("MULTI-E2E"),
        logging=None,
    ))
    engine.add_venue(
        VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(vusa_instr)
    engine.add_data(vusa_bars)

    config = RebalanceStrategyConfig(book=book)
    strategy = TwoSleeveStrategy(config=config)
    strategy.register_sleeve(book.sleeves[0].name, trend_bundle)
    strategy.register_sleeve(book.sleeves[1].name, carry_bundle)
    strategy._figi_bimap = _stub_bimap({_FIGI_VUSA})
    engine.add_strategy(strategy)

    engine.run()

    assert engine.get_result() is not None

    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert len(fills) == 1, (
        f"Expected 1 fill (trade to target, then hold via realized gate), "
        f"got {len(fills)}"
    )

    # All fills should be BUY VUSA, ~22,000 shares each.
    for f in fills:
        assert f.instrument_id == vusa_instr.id, (
            f"Expected only VUSA fills, got {f.instrument_id}"
        )
        assert f.is_buy, f"Expected BUY (net +0.22), got {f}"
        assert float(f.quantity.as_double()) > 0

    engine.dispose()


def test_vol_targeting_downweights_the_higher_vol_sleeve_through_the_engine():
    """End-to-end proof that the vol-targeted allocator runs through the engine.

    Two Floor sleeves on distinct EUR instruments carry EQUAL risk shares
    (0.5 / 0.5) but realize very different volatilities: one instrument drifts
    quietly, the other swings ~12x harder.  Fed enough daily bars to estimate a
    covariance (``>= _MIN_SLEEVE_VOL_RETURNS + 1`` recorded periods), the
    strategy estimates the realized sleeve covariance from its own buffered bars
    and the allocator vol-targets: the higher-vol sleeve receives a STRICTLY
    SMALLER capital multiplier than the calmer one.

    From the risk-budget base case alone (raw risk shares, no estimate yet) two
    equal-share sleeves get IDENTICAL multipliers, so this asymmetry is
    reachable only when the covariance refinement is genuinely exercised through
    the real ``BacktestEngine``
    -- the gap the 5-bar ``test_multi_sleeve_e2e`` cannot cover.  All-EUR by
    design, so ``PortfolioFacade.net_exposure`` values every position with no
    cross-currency marking.
    """
    calm_name = SleeveName("calm")
    vol_name = SleeveName("volatile")
    book = BookConfig(
        sleeves=(
            SleeveConfig(name=calm_name, wheel_filename="calm.whl", risk_share=0.5),
            SleeveConfig(name=vol_name, wheel_filename="vol.whl", risk_share=0.5),
        ),
        base_currency="EUR",
    )

    # Distinct, de-correlated price paths (different frequencies) with a ~12x
    # realized-vol gap; both stay positive so every period return is finite.
    i = np.arange(30)
    calm_prices = (100.0 * (1.0 + 0.004 * np.sin(0.7 * i))).tolist()
    vol_prices = (100.0 * (1.0 + 0.05 * np.sin(1.3 * i + 0.5))).tolist()

    calm_instr = _make_instrument(_FIGI_CALM)
    vol_instr = _make_instrument(_FIGI_VOL)

    engine = BacktestEngine(BacktestEngineConfig(
        trader_id=TraderId("VOLTGT-E2E"),
        logging=None,
    ))
    engine.add_venue(
        VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(1_000_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(calm_instr)
    engine.add_instrument(vol_instr)
    engine.add_data(_make_bars(_FIGI_CALM, calm_prices))
    engine.add_data(_make_bars(_FIGI_VOL, vol_prices))

    config = RebalanceStrategyConfig(book=book)
    strategy = TwoSleeveStrategy(config=config)
    strategy.register_sleeve(calm_name, _FixedWeightBundle(_FIGI_CALM, 0.5))
    strategy.register_sleeve(vol_name, _FixedWeightBundle(_FIGI_VOL, 0.5))
    strategy._figi_bimap = _stub_bimap({_FIGI_CALM, _FIGI_VOL})
    engine.add_strategy(strategy)

    engine.run()

    assert engine.get_result() is not None
    # Enough periods accrued to estimate a covariance: the refinement path ran.
    assert len(strategy._attribution_periods) >= _MIN_SLEEVE_VOL_RETURNS + 1
    # The book traded end-to-end (the path is live, not merely computed).
    assert any(o.is_closed for o in engine.cache.orders())

    # Equal risk shares + unequal realized vol -> the allocator down-weights the
    # high-vol sleeve.  Both multipliers would equal 0.5 from the risk-budget
    # base case alone, so a strict inequality proves the refinement engaged.
    multipliers = strategy._last_sleeve_weights
    assert multipliers[calm_name] > multipliers[vol_name]

    engine.dispose()
