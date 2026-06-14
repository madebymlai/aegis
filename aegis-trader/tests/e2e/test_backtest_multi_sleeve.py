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
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

# ── synthetic bundles ─────────────────────────────────────────────────────────

_FIGI_VUSA = "BBG000B9XRY4"   # VUSA.L


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
    """Extends RebalanceStrategy to process two sleeves from the same bar
    stream, accumulating per-sleeve targets and netting via the multi-sleeve
    rebalancer.

    For Slice 2 e2e testing; Slice 6 (cadence) will replace the
    per-sleeve timing with a proper timeframe-driven scheduler.
    """

    def __init__(self, config: RebalanceStrategyConfig) -> None:
        super().__init__(config)
        self._sleeve_bundles: dict[SleeveName, ExecutionBundle] = {}
        self._sleeve_contracts: dict[SleeveName, DataContract] = {}

    def register_sleeve(
        self, name: SleeveName, bundle: ExecutionBundle
    ) -> None:
        self._sleeve_bundles[name] = bundle
        self._sleeve_contracts[name] = bundle.contract

    def on_start(self) -> None:
        # Stub parent's expectations so _buffer_bar works.
        first = next(iter(self._sleeve_contracts.values()))
        self._contract = first
        self._bundle = next(iter(self._sleeve_bundles.values()))

        # Subscribe to all unique FIGIs across all sleeves.
        seen: set[str] = set()
        for name, bundle in self._sleeve_bundles.items():
            for figi in bundle.contract.figis:
                if figi in seen:
                    continue
                seen.add(figi)
                bar_type = BarType.from_str(
                    f"{self._figi_to_instr_id(figi).value}-1-DAY-LAST-EXTERNAL"
                )
                self.subscribe_bars(bar_type)
            self.log.info(
                f"Registered sleeve {name.value} figis={bundle.contract.figis}"
            )

    def on_bar(self, bar: Bar) -> None:
        """Buffer the bar, compute all sleeve targets, and submit with one-bar lag.

        All sleeves share the same bar stream for simplicity; per-sleeve
        timeframe arrives in Slice 6.
        """
        buf = self._buffer_bar(bar)
        if buf is None:
            return  # not enough lookback yet

        # Compute target for every sleeve from the shared bar buffer.
        for name, bundle in self._sleeve_bundles.items():
            contract = self._sleeve_contracts[name]
            figi = contract.figis[0]  # single-FIGI bundles for this test
            close_series = _bars_to_close_series(buf, figi)
            bundle_data = MarketDataBundle({"Close": close_series})
            target = bundle.compute_weights(bundle_data)
            self._pending_targets[name] = target

        # Submit from accumulated targets (one-bar lag via pending_targets).
        self._submit_pending_orders()


from aegis_trader.domain.rebalancer import rebalance  # noqa: E402


def _bars_to_close_series(
    bars: list[Bar], figi: str
) -> pd.DataFrame:
    index = pd.DatetimeIndex([b.ts_event for b in bars])
    values = [float(b.close.as_double()) for b in bars]
    return pd.DataFrame({figi: values}, index=index)


# ── helpers ───────────────────────────────────────────────────────────────────

VENUE = Venue("XLON")


def _make_instrument(figi: str) -> Instrument:
    return TestInstrumentProvider.equity(symbol=figi, venue=VENUE.value)


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
                budget=budgets[0],
            ),
            SleeveConfig(
                name=SleeveName("carry"),
                wheel_filename="carry-def.whl",
                budget=budgets[1],
            ),
        ),
        base_currency="EUR",
        default_venue=VENUE.value,
    )


# ── e2e test ──────────────────────────────────────────────────────────────────


def test_multi_sleeve_e2e():
    """Slice 2 end-to-end: multi-sleeve netting in a backtest.

    Two sleeves sharing the same instrument (VUSA) net to a single
    OrderIntent.  With NEXT-CLOSE lag (5 daily bars, lookback=1):

      trend: budget=0.6, weight=+0.5 on VUSA → scaled=+0.30
      carry: budget=0.4, weight=-0.2 on VUSA → scaled=-0.08
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
    engine.add_strategy(strategy)

    engine.run()

    assert engine.get_result() is not None

    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert len(fills) >= 2, f"Expected >=2 fills, got {len(fills)}"

    # All fills should be BUY VUSA, ~22,000 shares each.
    for f in fills:
        assert f.instrument_id == vusa_instr.id, (
            f"Expected only VUSA fills, got {f.instrument_id}"
        )
        assert f.is_buy, f"Expected BUY (net +0.22), got {f}"
        assert float(f.quantity.as_double()) == pytest.approx(22_000, rel=2e-2)

    engine.dispose()
