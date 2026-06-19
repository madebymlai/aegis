"""E2E for v0j.4: a futures sleeve crossing a roll boundary rolls automatically.

The capstone of the asset-agnostic instrument identity epic (aegis-rd-v0j).  A
``FuturesRef`` sleeve establishes a position in the *front* dated contract via
the normal alpha/drift path; when the as-of futures calendar advances past the
roll boundary the base-tick roll step fires a mandatory, exposure-neutral pair
(SELL the front, BUY the next) on the *resolved* contracts — bypassing the drift
band but riding the same submit / RiskEngine path.  Afterwards the book holds the
next contract with the front flat, and the drift path never thrashes the stale
contract (the realized ESH5 position folds back to its FuturesRef).

What this proves end-to-end:
  - FuturesRef nets in InstrumentRef space (the front position is established).
  - The roll is detected on the base tick when the resolved contract changes.
  - The roll is exposure-neutral (exit qty == enter qty == held qty).
  - The book settles on the rolled-into contract and does not re-buy the front.

N.B. one BacktestEngine per process (see conftest); ``logging=None``.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from aegis_data.roll import DatedContract
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, TraderId, Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Currency, Money
from conftest import eur_future

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    FuturesRef,
    LockedExecutionPlan,
    MarketDataBundle,
)

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

VENUE = Venue("XCME")
_FRONT = InstrumentId.from_str("ESZ4.XCME")  # held first
_NEXT = InstrumentId.from_str("ESH5.XCME")  # rolled into
_FUT = FuturesRef(root="ES", dataset="cme")
_NS_PER_DAY = 86_400_000_000_000
_ROLL_DATE = date(1970, 1, 5)  # day index 4 (epoch-anchored bars)


class _ConstantWeightBundle(ExecutionBundle):
    """A single-FuturesRef sleeve with a constant target weight.

    Constant weight + constant price ⇒ the book trades to target once, then
    holds (within the drift band), so the *only* post-establishment activity is
    the roll — isolating the roll behaviour under test.
    """

    def __init__(self, weight: float = 0.5) -> None:
        self._weight = weight
        contract = DataContract(
            refs=(_FUT,),
            required_arrays=("Close",),
            base_currency="EUR",
            required_fx_currencies=(),
            timeframe="1D",
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="roll-synth",
            role="synth",
            candidate_key="roll-key",
            component_source_hashes={},
            refs=(_FUT,),
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
            symbols=("ES",),
            currency_by_symbol={"ES": "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self, prices: MarketDataBundle, *, fx_series=None,
    ) -> pd.DataFrame:
        close = prices.array("Close")
        df = pd.DataFrame({_FUT: [self._weight] * len(close)}, index=close.index)
        df.columns.name = "instrument_ref"
        return df


_STEP_DATE = date(1970, 1, 9)  # day 8 — after the roll + rolled-contract warmup


class _StepWeightBundle(ExecutionBundle):
    """Target steps up once the strategy's bars cross ``_STEP_DATE``.

    Used to prove a post-roll drift lands on the rolled-into contract, not the
    stale front.  The step keys off the bar *date* (not price), so both contracts
    can hold one flat price and the roll stays value-neutral.
    """

    def __init__(self, base: float = 0.5, step: float = 0.3) -> None:
        self._base = base
        self._step = step
        contract = DataContract(
            refs=(_FUT,), required_arrays=("Close",), base_currency="EUR",
            required_fx_currencies=(), timeframe="1D", lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="roll-step", role="synth", candidate_key="roll-step-key",
            component_source_hashes={}, refs=(_FUT,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy", component_id="synth_strat", module="synth",
                input_names=(), output_names=(), params={},
            ),
            indicators=(), gross_cap=1.0, net_cap=None, direction="both",
            symbols=("ES",), currency_by_symbol={"ES": "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle, *, fx_series=None) -> pd.DataFrame:
        close = prices.array("Close")
        last_date = close.index[-1].date()
        w = self._base + self._step if last_date >= _STEP_DATE else self._base
        df = pd.DataFrame({_FUT: [w] * len(close)}, index=close.index)
        df.columns.name = "instrument_ref"
        return df


def _make_bars(instrument: Instrument, prices: list[float], start_day: int = 0) -> list[Bar]:
    bar_type = BarType.from_str(f"{instrument.id.value}-1-DAY-LAST-EXTERNAL")
    bars: list[Bar] = []
    for i, px in enumerate(prices):
        ts = (start_day + i) * _NS_PER_DAY
        p = instrument.make_price(px)
        bars.append(Bar(
            bar_type=bar_type, open=p, high=p, low=p, close=p,
            volume=instrument.make_qty(1000), ts_event=ts, ts_init=ts,
        ))
    return bars


def _contract_chains() -> dict[str, tuple[DatedContract, ...]]:
    """Provider-loaded dated contracts whose expiry rule rolls on _ROLL_DATE."""
    return {
        "ES": (
            DatedContract("ESZ4", date(1970, 1, 12)),
            DatedContract("ESH5", date(1970, 1, 30)),
        )
    }


def _make_book() -> BookConfig:
    return BookConfig(
        sleeves=(SleeveConfig(
            name=SleeveName("trend_fut"), wheel_filename="trend_fut.whl", risk_share=1.0,
        ),),
        base_currency="EUR",
    )


def test_futures_sleeve_rolls_across_boundary():
    front = eur_future("ESZ4", VENUE.value)
    nxt = eur_future("ESH5", VENUE.value)

    # 8 daily bars at a flat price for both contracts: roll boundary at day 4.
    flat = [100.0] * 8
    bars = _make_bars(front, flat) + _make_bars(nxt, flat)
    bars.sort(key=lambda b: b.ts_event)

    engine = BacktestEngine(BacktestEngineConfig(
        trader_id=TraderId("ROLL-E2E"), logging=None,
    ))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(1_000_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(front)
    engine.add_instrument(nxt)
    engine.add_data(bars)

    config = RebalanceStrategyConfig(
        book=_make_book(), futures_contract_chains=_contract_chains()
    )
    strategy = RebalanceStrategy(config=config)
    strategy.register_sleeve(_make_book().sleeves[0].name, _ConstantWeightBundle(weight=0.5))
    # No injected bimap: on_start resolves the FuturesRef from provider-loaded
    # dated contracts, then the same chain advances it at the roll.
    engine.add_strategy(strategy)

    engine.run()

    fills = [o for o in engine.cache.orders() if o.is_closed]
    front_buys = [f for f in fills if f.instrument_id == _FRONT and f.is_buy]
    front_sells = [f for f in fills if f.instrument_id == _FRONT and not f.is_buy]
    next_buys = [f for f in fills if f.instrument_id == _NEXT and f.is_buy]
    next_sells = [f for f in fills if f.instrument_id == _NEXT and not f.is_buy]

    def _qty(order) -> float:
        return float(order.quantity.as_double())

    # Established the front once, rolled once, never thrashed.
    assert len(front_buys) == 1, (
        f"expected one front-contract BUY (establish), got "
        f"{[(_qty(f)) for f in front_buys]}; "
        f"a second front BUY means the rolled position did not fold back to its FuturesRef"
    )
    assert len(front_sells) == 1, f"expected one front-contract SELL (roll exit), got {len(front_sells)}"
    assert len(next_buys) == 1, f"expected one next-contract BUY (roll enter), got {len(next_buys)}"
    assert next_sells == [], "the rolled-into contract must not be sold"

    # The roll is exposure-neutral: it exits and enters the full held quantity.
    held_qty = _qty(front_buys[0])
    assert _qty(front_sells[0]) == held_qty
    assert _qty(next_buys[0]) == held_qty

    # The book settles holding the rolled-into contract; the front is flat.
    open_positions = engine.cache.positions_open()
    assert len(open_positions) == 1, (
        f"expected exactly one open position (the rolled-into contract), got "
        f"{[(p.instrument_id.value, _qty(p)) for p in open_positions]}"
    )
    assert open_positions[0].instrument_id == _NEXT
    assert open_positions[0].is_long
    assert _qty(open_positions[0]) == held_qty

    engine.dispose()


def test_drift_follows_rolled_contract():
    """After the roll, a target change drifts onto the rolled-into contract
    (resolved-contract space) — never the stale front (gap A of v0j.4).

    The bimap is refreshed at the roll, so a post-roll drift order resolves the
    FuturesRef to the *current* contract.  Without the refresh, drift would
    re-buy the front contract the position was just rolled out of.
    """
    front = eur_future("ESZ4", VENUE.value)
    nxt = eur_future("ESH5", VENUE.value)
    flat = [100.0] * 14  # equal price on both contracts ⇒ the roll is value-neutral
    bars = _make_bars(front, flat) + _make_bars(nxt, flat)
    bars.sort(key=lambda b: b.ts_event)

    engine = BacktestEngine(BacktestEngineConfig(
        trader_id=TraderId("ROLL-DRIFT-E2E"), logging=None,
    ))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(1_000_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(front)
    engine.add_instrument(nxt)
    engine.add_data(bars)

    config = RebalanceStrategyConfig(
        book=_make_book(), futures_contract_chains=_contract_chains()
    )
    strategy = RebalanceStrategy(config=config)
    strategy.register_sleeve(_make_book().sleeves[0].name, _StepWeightBundle())
    engine.add_strategy(strategy)

    engine.run()

    def _qty(order) -> float:
        return float(order.quantity.as_double())

    fills = [o for o in engine.cache.orders() if o.is_closed]
    front_buys = [f for f in fills if f.instrument_id == _FRONT and f.is_buy]
    front_sells = [f for f in fills if f.instrument_id == _FRONT and not f.is_buy]
    next_buys = [f for f in fills if f.instrument_id == _NEXT and f.is_buy]

    # Front: established once, rolled out once, NEVER re-bought (no stale-contract drift).
    assert len(front_buys) == 1, (
        f"front contract must not be re-bought after the roll; got "
        f"{[_qty(f) for f in front_buys]} (stale-bimap drift)"
    )
    assert len(front_sells) == 1, f"expected one front SELL (roll exit), got {len(front_sells)}"

    # The post-roll target step drifted MORE onto the rolled-into contract.
    assert len(next_buys) >= 2, (
        f"expected roll-enter + a drift add on the rolled-into contract, got {len(next_buys)}"
    )

    open_positions = engine.cache.positions_open()
    assert len(open_positions) == 1, (
        f"book must hold only the rolled-into contract, got "
        f"{[(p.instrument_id.value, _qty(p)) for p in open_positions]}"
    )
    pos = open_positions[0]
    assert pos.instrument_id == _NEXT and pos.is_long
    # Converged to the stepped-up target on the rolled-into contract; the
    # establish/roll moved only the base weight, so drift added on top.
    assert _qty(pos) > _qty(front_buys[0]), (
        f"rolled-into position {_qty(pos)} should exceed the rolled (base) qty "
        f"{_qty(front_buys[0])} — the post-roll step must drift onto it"
    )

    engine.dispose()
