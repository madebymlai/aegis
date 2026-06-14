"""E2E test for the tracer slice: single sleeve → NEXT-CLOSE order, backtest.

Validates that a RebalanceStrategy running on synthetic daily bars +
a synthetic single-instrument ExecutionBundle emits the expected order with
one-bar execution lag and no look-ahead.

N.B. NautilusTrader's BacktestEngine internally initialises a global logger
once; only one BacktestEngine may be constructed per process.  We build one
engine and run a single end-to-end scenario (the rebalancer edge cases are
covered by the pure-domain unit tests in tests/unit/).
"""

from __future__ import annotations

import pandas as pd
import pytest
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, TraderId, Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider

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
from aegis_trader.execution.figi_resolver import FigiInstrumentResolver
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

# ── synthetic bundle ──────────────────────────────────────────────────────────

_SYNTH_FIGI = "BBG000B9XRY4"  # VUSA.L FIGI (nascent; stub-resolved to VUSA.XLON)


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
            run_id="synth-run-001",
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


def _make_instrument() -> Instrument:
    return TestInstrumentProvider.equity(
        symbol=_SYNTH_FIGI,
        venue=VENUE.value,
    )


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
        default_venue=VENUE.value,
    )


class _StubFigiResolver(FigiInstrumentResolver):
    """Resolver that returns convention-based InstrumentIds for testing."""

    def resolve(self, figis, *, transport=None):
        return {figi: InstrumentId.from_str(f"{figi}.{VENUE.value}") for figi in figis}


# ── test ──────────────────────────────────────────────────────────────────────


def test_tracer_e2e():
    """Slice 1 end-to-end: next-close order timing, no-lookahead.

    5 daily bars with lookback=1:
      bar 0: buffer=[100] → need 2 bars, skip
      bar 1: buffer=[100,101] → compute target 0.5, store as pending
      bar 2: buffer=[101,102] → submit from pending (50,000 BUY), compute new
      bar 3: buffer=[102,103] → submit from pending (50,000 BUY)
      bar 4: buffer=[103,104] → submit from pending (50,000 BUY)

    Expected: ≥2 filled BUY orders of ~50,000 shares each.
    The first fill proves NEXT-CLOSE execution (one-bar lag).
    """
    instrument = _make_instrument()
    book = _make_book()
    bundle = _SyntheticBundle(weight=0.5)
    bars = _make_bars([100.0, 101.0, 102.0, 103.0, 104.0], start_ns=0)

    engine = BacktestEngine(BacktestEngineConfig(
        trader_id=TraderId("TRACER-E2E"),
        logging=None,
    ))
    engine.add_venue(
        VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(instrument)
    engine.add_data(bars)

    config = RebalanceStrategyConfig(book=book, figi_resolver=_StubFigiResolver())
    strategy = RebalanceStrategy(config=config)
    strategy._bundle = bundle
    engine.add_strategy(strategy)

    engine.run()

    assert engine.get_result() is not None

    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert len(fills) >= 2, f"Expected >=2 fills, got {len(fills)}"
    for f in fills:
        assert f.is_buy
        assert float(f.quantity.as_double()) == pytest.approx(50_000, rel=1e-2)

    engine.dispose()
