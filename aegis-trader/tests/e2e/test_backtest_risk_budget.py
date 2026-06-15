"""Risk-budget e2e: 5-year covariance vol-target budget and attribution."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import eur_equity
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, TraderId, Venue
from nautilus_trader.model.objects import Currency, Money

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
)

from aegis_trader.domain.allocator import covariance_book_vol
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.book_config import (
    BookConfig,
    DrawdownDeleverCurve,
    RiskGroup,
    SleeveConfig,
)
from aegis_trader.domain.rebalancer import rebalance
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_TREND = SleeveName("trend")
_TAIL = SleeveName("tail")
_FIGI = "BBG000B9XRY4"
_VENUE = Venue("XLON")


class _WarmupOnlyRebalanceStrategy(RebalanceStrategy):
    """Keep this e2e focused on the drawdown seam, not covariance warmup."""

    def _realized_sleeve_covariance(self):
        return None


class _FixedWeightBundle(ExecutionBundle):
    """Synthetic bundle that always targets one FIGI at a fixed weight."""

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
            run_id="drawdown-synth",
            role="synth",
            candidate_key="drawdown-synth-key",
            component_source_hashes={},
            figis=(figi,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="fixed_weight",
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
        df = pd.DataFrame({self._figi: [self._weight] * len(close)}, index=close.index)
        df.columns.name = "figi"
        return df


def test_five_year_covariance_risk_budget_hits_vol_target_and_attribution_reconciles():
    """Tracer for the commingled backtest invariant without external data/wheels.

    Five years of synthetic daily sleeve returns produce a realized covariance
    input.  The rebalancer must use the allocator seam (not static capital
    budgets): the higher-vol tail receives half the capital multiplier of the
    lower-vol trend in the zero-correlation limit, the book hits the configured
    annualized vol target, and attribution sums back to the realized NAV change.
    """
    days = 252 * 5
    x = np.linspace(0.0, 80.0 * np.pi, days)
    trend_returns = 0.10 / np.sqrt(252.0) * np.sin(x)
    tail_returns = 0.20 / np.sqrt(252.0) * np.cos(x)
    covariance = {
        _TREND: {
            _TREND: float(np.var(trend_returns, ddof=1) * 252.0),
            _TAIL: float(np.cov(trend_returns, tail_returns, ddof=1)[0, 1] * 252.0),
        },
        _TAIL: {
            _TREND: float(np.cov(trend_returns, tail_returns, ddof=1)[0, 1] * 252.0),
            _TAIL: float(np.var(tail_returns, ddof=1) * 252.0),
        },
    }

    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.5,
                group=RiskGroup.FLOOR,
            ),
            SleeveConfig(
                name=_TAIL,
                wheel_filename="tail.whl",
                risk_share=0.5,
                group=RiskGroup.TARGET,
            ),
        ),
        book_vol_target=0.09,
    )

    target = _one_row_target
    deltas = rebalance(
        {
            _TREND: target({"TREND": 1.0}),
            _TAIL: target({"TAIL": 1.0}),
        },
        book,
        realized_covariance=covariance,
    )
    weights = {delta.figi.value: delta.delta for delta in deltas}

    assert weights["TAIL"] == pytest.approx(weights["TREND"] / 2.0, rel=0.02)
    assert covariance_book_vol(
        {_TREND: weights["TREND"], _TAIL: weights["TAIL"]},
        covariance,
    ) == pytest.approx(book.book_vol_target)

    nav = 1_000_000.0
    periods = [
        AttributionPeriod(
            nav=nav,
            realized_weights=weights,
            sleeve_targets={_TREND: {"TREND": 1.0}, _TAIL: {"TAIL": 1.0}},
            closes={"TREND": 100.0, "TAIL": 100.0},
        ),
        AttributionPeriod(
            nav=nav,
            realized_weights=weights,
            sleeve_targets={_TREND: {"TREND": 1.0}, _TAIL: {"TAIL": 1.0}},
            closes={"TREND": 101.0, "TAIL": 98.0},
        ),
    ]
    attribution = compute_sleeve_attribution(
        periods,
        budgets={_TREND: 0.5, _TAIL: 0.5},
    )
    book_pnl = (
        weights["TREND"] * 0.01
        + weights["TAIL"] * -0.02
    ) * nav

    assert sum(attribution.values()) == pytest.approx(book_pnl)


def test_backtest_drawdown_delever_engages_in_worst_window_and_returns_are_measured():
    """Backtest seam: NAV drawdown from the engine drives a book-level de-lever.

    A five-year synthetic path opens with an early crash, stays in the trough,
    then heals.  The strategy computes drawdown from its recorded NAV path and
    passes it to the allocator; the observable effect is a sell order while the
    bundle still asks for a constant long target.
    """
    prices = _five_year_drawdown_prices()
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.80,
                group=RiskGroup.FLOOR,
            ),
        ),
        base_currency="EUR",
        drawdown_delever=DrawdownDeleverCurve(
            start_drawdown=0.05,
            end_drawdown=0.20,
            floor_multiplier=0.25,
        ),
    )

    instrument = eur_equity(_FIGI, _VENUE.value)
    engine = BacktestEngine(
        BacktestEngineConfig(trader_id=TraderId("DD-E2E"), logging=None)
    )
    engine.add_venue(
        _VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(instrument)
    engine.add_data(_bars(instrument, prices))

    strategy = _WarmupOnlyRebalanceStrategy(
        config=RebalanceStrategyConfig(book=book)
    )
    strategy.register_sleeve(_TREND, _FixedWeightBundle(_FIGI, 1.0))
    strategy._figi_bimap = {_FIGI: InstrumentId.from_str(f"{_FIGI}.{_VENUE.value}")}
    engine.add_strategy(strategy)

    engine.run()

    returns = _finite_return_values(engine.portfolio.analyzer.returns())
    assert returns
    assert min(returns) < 0.0

    peak = max(strategy._nav_history)
    worst_drawdown = max(1.0 - nav / peak for nav in strategy._nav_history)
    assert worst_drawdown >= 0.20

    closed_orders = [order for order in engine.cache.orders() if order.is_closed]
    assert any(order.is_sell for order in closed_orders), (
        "drawdown de-lever should sell down exposure despite a constant long sleeve"
    )

    engine.dispose()


def _one_row_target(figi_to_weight: dict[str, float]):
    df = pd.DataFrame(
        {k: [v] for k, v in figi_to_weight.items()},
        index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
    )
    df.columns.name = "figi"
    return df


def _five_year_drawdown_prices() -> list[float]:
    calm = np.full(10, 100.0)
    crash = np.array([60.0])
    trough = np.full(252 * 2, 60.0)
    recovery = np.linspace(60.0, 100.0, 252)
    healed = np.full(252 * 2 - 11, 100.0)
    return [
        float(price)
        for price in np.concatenate([calm, crash, trough, recovery, healed])
    ]


def _bars(instrument, prices: list[float]) -> list[Bar]:
    bar_type = BarType.from_str(f"{instrument.id.value}-1-DAY-LAST-EXTERNAL")
    interval = 86_400_000_000_000
    bars: list[Bar] = []
    ts = 0
    for price in prices:
        p = instrument.make_price(price)
        bars.append(
            Bar(
                bar_type=bar_type,
                open=p,
                high=p,
                low=p,
                close=p,
                volume=instrument.make_qty(1000),
                ts_event=ts,
                ts_init=ts,
            )
        )
        ts += interval
    return bars


def _finite_return_values(raw_returns) -> list[float]:
    if isinstance(raw_returns, dict):
        arrays = [np.asarray(value, dtype=float).ravel() for value in raw_returns.values()]
        if not arrays:
            return []
        values = np.concatenate(arrays)
    else:
        values = np.asarray(raw_returns, dtype=float).ravel()
    return [float(value) for value in values if np.isfinite(value)]
