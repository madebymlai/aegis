"""E2E test for Slice 8: RiskEngine guards + kill-switch.

Validates two defense-in-depth behaviours:

1. **RiskEngineConfig wiring** — the RiskEngine receives per-instrument
   max-notional caps computed from NAV by the ``RiskGuard`` and honours the
   configured rate limits.

2. **Kill-switch halts trading** — when ``TradingState.HALTED`` is set on the
   RiskEngine, all new order submissions are denied before reaching the venue.

The ``RiskGuard`` unit tests cover NAV-relative cap computation exhaustively
(tests/unit/test_risk_guard.py).
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, TraderId, Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.risk.config import RiskEngineConfig
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
from aegis_trader.domain.risk_guard import compute_risk_engine_max_notionals
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

# ── synthetic bundle ──────────────────────────────────────────────────────────

_SYNTH_FIGI = "BBG000B9XRY4"  # VUSA.L


class _SyntheticBundle(ExecutionBundle):
    """A bundle that returns a fixed target weight every bar."""

    def __init__(self, weight: float = 0.5) -> None:
        self._weight = weight
        contract = DataContract(
            figis=(_SYNTH_FIGI,),
            required_arrays=("Close",),
            base_currency="EUR",
            required_fx_currencies=(),
            timeframe="1D",
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="risk-synth-001",
            role="synth",
            candidate_key="synth-key",
            component_source_hashes={},
            figis=(_SYNTH_FIGI,),
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
            symbols=(_SYNTH_FIGI,),
            currency_by_symbol={_SYNTH_FIGI: "EUR"},
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
            {_SYNTH_FIGI: [self._weight] * n},
            index=close.index,
        )
        df.columns.name = "figi"
        return df


# ── helpers ───────────────────────────────────────────────────────────────────

VENUE = Venue("XLON")
_STARTING_NAV = 100_000.0


def _make_instrument() -> Instrument:
    return eur_equity(_SYNTH_FIGI, VENUE.value)


def _make_bars(prices: list[float], start_ns: int = 0) -> list[Bar]:
    instrument = _make_instrument()
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


def _make_book() -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("tracer"),
                wheel_filename="tracer-abc123.whl",
                budget=1.0,
            ),
        ),
        base_currency="EUR",
    )


def _build_engine(
    trader_id: str,
    risk_config: RiskEngineConfig | None = None,
) -> BacktestEngine:
    engine_cfg = BacktestEngineConfig(
        trader_id=TraderId(trader_id),
        logging=None,
        risk_engine=risk_config or RiskEngineConfig(),
    )
    engine = BacktestEngine(engine_cfg)
    engine.add_venue(
        VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(_STARTING_NAV, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(_make_instrument())
    return engine


# ── tests ─────────────────────────────────────────────────────────────────────


def test_risk_engine_config_wired_from_risk_guard():
    """Slice 8: RiskEngineConfig respects RiskGuard-computed max notionals
    and rate limits.

    Verifies the wiring: RiskGuardConfig → RiskEngineConfig → RiskEngine.
    """
    instr_id_str = f"{_SYNTH_FIGI}.{VENUE.value}"

    # Compute what the RiskGuard would produce for the starting NAV.
    max_notionals = compute_risk_engine_max_notionals(
        nav=_STARTING_NAV,
        instrument_ids=[instr_id_str],
        fraction=0.25,
    )

    # Build a RiskEngineConfig with those values (mimicking RiskGuard output).
    risk_cfg = RiskEngineConfig(
        max_notional_per_order=dict(max_notionals),
        max_order_submit_rate="5/00:00:01",
        max_order_modify_rate="3/00:00:01",
        bypass=False,
    )

    engine = _build_engine("RISK-CFG-E2E", risk_config=risk_cfg)
    bars = _make_bars([100.0, 101.0])
    engine.add_data(bars)

    book = _make_book()
    bundle = _SyntheticBundle(weight=0.5)
    config = RebalanceStrategyConfig(book=book)
    strategy = RebalanceStrategy(config=config)
    strategy.register_sleeve(book.sleeves[0].name, bundle)
    strategy._figi_bimap = {_SYNTH_FIGI: InstrumentId.from_str(instr_id_str)}
    engine.add_strategy(strategy)

    engine.run()

    risk_engine = engine.kernel.risk_engine

    from nautilus_trader.core.rust.model import TradingState

    # RiskEngine should be ACTIVE (not bypassed).
    assert risk_engine.trading_state == TradingState.ACTIVE, (
        "Expected ACTIVE at startup"
    )
    assert risk_engine.is_bypassed is False

    # Max notional per order — should match our computed caps.
    max_not_setting = risk_engine.max_notional_per_order(
        InstrumentId.from_str(instr_id_str)
    )
    assert max_not_setting is not None, (
        f"Expected max_notional for {instr_id_str} to be set"
    )
    assert int(max_not_setting) == max_notionals[instr_id_str], (
        f"Expected max notional {max_notionals[instr_id_str]}, got {max_not_setting}"
    )

    # Rate limits.
    submit = risk_engine.max_order_submit_rate()
    assert submit == (5, pd.Timedelta("1s")), (
        f"Expected submit rate (5, 1s), got {submit}"
    )
    modify = risk_engine.max_order_modify_rate()
    assert modify == (3, pd.Timedelta("1s")), (
        f"Expected modify rate (3, 1s), got {modify}"
    )

    engine.dispose()


def test_kill_switch_halts_all_trading():
    """Slice 8: The kill-switch (TradingState.HALTED) denies all new orders.

    HALTED is set on the RiskEngine after the engine has initialised but
    before the strategy submits orders.  Expected: every order submitted is
    denied by the RiskEngine before reaching the venue.
    """
    book = _make_book()
    bundle = _SyntheticBundle(weight=0.5)
    bars = _make_bars([100.0, 101.0, 102.0, 103.0, 104.0])

    engine = _build_engine("RISK-HALT-E2E")
    engine.add_data(bars)

    config = RebalanceStrategyConfig(book=book)
    strategy = RebalanceStrategy(config=config)
    strategy.register_sleeve(book.sleeves[0].name, bundle)
    strategy._figi_bimap = {
        _SYNTH_FIGI: InstrumentId.from_str(f"{_SYNTH_FIGI}.{VENUE.value}")
    }
    engine.add_strategy(strategy)

    # HALT before the run processes any bar events.
    from nautilus_trader.core.rust.model import TradingState
    engine.kernel.risk_engine.set_trading_state(TradingState.HALTED)

    engine.run()

    result = engine.get_result()
    assert result is not None

    all_orders = engine.cache.orders()
    # When HALTED, orders should be denied immediately.
    from nautilus_trader.model.enums import OrderStatus
    denied = [o for o in all_orders if o.status == OrderStatus.DENIED]
    filled = [o for o in all_orders if o.status == OrderStatus.FILLED]

    assert len(denied) >= 1, (
        f"Expected >=1 DENIED order due to HALTED state, "
        f"got {[(o.status_string(),) for o in all_orders]}"
    )
    assert len(filled) == 0, (
        f"Expected 0 fills when HALTED, got {len(filled)}"
    )

    engine.dispose()
