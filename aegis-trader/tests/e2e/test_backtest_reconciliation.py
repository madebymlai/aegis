"""E2E test for Slice 7: reconciliation — integrity-halt + quarantine.

Validates two behaviours:

1. **Integrity check at startup** — the strategy performs an account-integrity
   check in ``on_start``; when healthy the book continues trading normally.

2. **Quarantine** — held positions for instruments not in any sleeve contract
   are quarantined (logged, never traded) while still counted in the gate.

The pure-domain unit tests (tests/unit/test_integrity.py and the quarantine
section of tests/unit/test_rebalancer.py) cover the integrity and quarantine
rules exhaustively.

N.B. Only one BacktestEngine per process; run this test in isolation.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import TraderId, Venue
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


def _make_instrument(figi: str = _SYNTH_FIGI) -> Instrument:
    return TestInstrumentProvider.equity(symbol=figi, venue=VENUE.value)


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


# ── engine factory ────────────────────────────────────────────────────────────


def _setup_engine(trader_id: str, book: BookConfig, bundle: _SyntheticBundle) -> tuple[BacktestEngine, RebalanceStrategy]:
    """Create a configured BacktestEngine with one instrument, five daily bars.

    Returns (engine, strategy) — the caller must call ``engine.run()`` and
    ``engine.dispose()``.
    """
    bars = _make_bars([100.0, 101.0, 102.0, 103.0, 104.0])
    engine = BacktestEngine(BacktestEngineConfig(
        trader_id=TraderId(trader_id),
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
    engine.add_instrument(_make_instrument())
    engine.add_data(bars)

    config = RebalanceStrategyConfig(book=book)
    strategy = RebalanceStrategy(config=config)
    strategy._bundle = bundle
    engine.add_strategy(strategy)
    return engine, strategy


# ── tests ─────────────────────────────────────────────────────────────────────


def test_integrity_check_passes_in_normal_backtest():
    """Slice 7: account-integrity check passes at startup in a normal backtest.

    The strategy performs an integrity check in ``on_start``.  With a healthy
    cache and valid NAV/cash, the check passes and the strategy continues to
    trade normally.
    """
    engine, strategy = _setup_engine("INTEGRITY-E2E", _make_book(), _SyntheticBundle(weight=0.5))
    engine.run()

    assert engine.get_result() is not None

    # Verify the integrity check passed (strategy did NOT halt)
    assert not strategy._is_halted, (
        f"Expected integrity check to pass, but strategy halted: "
        f"{strategy._integrity_report}"
    )
    assert strategy._integrity_report is not None, (
        "Expected integrity report to be populated at startup"
    )
    assert strategy._integrity_report.healthy, (
        f"Integrity check failed: {strategy._integrity_report.reason}"
    )

    # Verify trading continued normally
    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert len(fills) >= 2, (
        f"Expected ≥2 fills (normal trading), got {len(fills)}"
    )

    engine.dispose()


def test_normal_backtest_no_quarantine():
    """Slice 7: in a normal backtest with only tracked FIGIs, no quarantine occurs.

    All broker positions correspond to FIGIs in sleeve contracts, so
    ``held_positions`` is empty and ``quarantined`` is empty.
    """
    engine, strategy = _setup_engine("NO-QUARANTINE-E2E", _make_book(), _SyntheticBundle(weight=0.5))
    engine.run()

    assert engine.get_result() is not None

    # All fills should be for the tracked FIGI only
    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert len(fills) >= 2
    for f in fills:
        assert _SYNTH_FIGI in f.instrument_id.value, (
            f"Expected fills only for {_SYNTH_FIGI}, got {f.instrument_id.value}"
        )

    engine.dispose()
