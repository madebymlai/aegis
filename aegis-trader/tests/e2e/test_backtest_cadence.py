"""E2E test for Slice 6: per-sleeve timeframe cadence + calendar-aware execution.

Validates:
  - Per-sleeve timeframe: each sleeve rebalances off its own bar-close
  - Debounce: one re-net per completed period (not per-instrument-bar churn)
  - Calendar-aware: only FIGIs with a fresh bar (open venue) get orders
  - Multi-day hold: a shut-venue sleeve holds; the open one trades

Two sleeves on divergent calendars:
  - trend_lse: VUSA on XLON (LSE)
  - trend_xetra: VOOL on XETR (Xetra)

Bar schedule: 4 days of VUSA bars; VOOL missing day 2 (XETR closed).
On day 2's completed-period rebalance (triggered at day 3), only VUSA
gets an order — VOOL is held because XETR was closed.

N.B. Only one BacktestEngine per process; run this test in isolation.
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

# ── synthetic bundles ─────────────────────────────────────────────────────────

_FIGI_VUSA = "BBG000B9XRY4"  # VUSA.L
_FIGI_VOOL = "BBG000BF46Y8"  # VOOL.DE

_NS_PER_DAY = 86_400_000_000_000


class _StepWeightBundle(ExecutionBundle):
    """A bundle whose target steps up once the close crosses a threshold.

    Under the realized-book gate an OPEN instrument needs a real (>band) trade
    each period to be distinguishable from a CLOSED one (which the calendar
    logic filters); the step guarantees that.
    """

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
        last = float(close.iloc[-1].iloc[0])
        w = self._weight if last < 102.0 else self._weight + 0.3
        df = pd.DataFrame(
            {self._figi: [w] * n},
            index=close.index,
        )
        df.columns.name = "figi"
        return df


# ── helpers ───────────────────────────────────────────────────────────────────

VENUE_LSE = Venue("XLON")
VENUE_XETRA = Venue("XETR")


def _make_instrument(figi: str, venue: Venue) -> Instrument:
    return eur_equity(figi, venue.value)


def _make_bars(
    figi: str, venue: Venue, prices: list[float], start_day: int = 0,
) -> list[Bar]:
    """Build a list of daily bars for *figi* on *venue* starting at *start_day*."""
    instrument = _make_instrument(figi, venue)
    bar_type = BarType.from_str(f"{instrument.id.value}-1-DAY-LAST-EXTERNAL")
    bars: list[Bar] = []
    for i, px in enumerate(prices):
        ts = (start_day + i) * _NS_PER_DAY
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
    return bars


def _make_book() -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("trend_lse"),
                wheel_filename="trend_lse.whl",
                risk_share=1.0,
            ),
            SleeveConfig(
                name=SleeveName("trend_xetra"),
                wheel_filename="trend_xetra.whl",
                risk_share=1.0,
            ),
        ),
        base_currency="EUR",
        # two fully-budgeted sleeves on disjoint venues → book gross 2.0
        max_book_gross=2.0,
    )


# ── e2e test ──────────────────────────────────────────────────────────────────


def test_cadence_calendar_aware():
    """Slice 6 end-to-end: two sleeves on divergent calendars.

    Bar schedule (lookback=1, needed=2):
      Day 0: VUSA=100.0, VOOL=200.0  (warmup)
      Day 1: VUSA=101.0, VOOL=201.0  → rebalance triggers day 2 → both fill
      Day 2: VUSA=102.0               (VOOL MISSING — XETR closed)
      Day 3: VUSA=103.0, VOOL=202.0  → rebalance triggers day 3 → VUSA fills; VOOL held

    Targets step up once close >= 102 so the OPEN instrument keeps trading under
    the realized gate; the CLOSED one is filtered by the calendar logic:
      - Period 1 (triggered day 2): VUSA BUY to target AND VOOL BUY to target
        (both venues had a day-1 bar).
      - Period 2 (triggered day 3): VUSA BUY the step-up delta ONLY — XETR was
        closed day 2 so VOOL has no fresh bar and is held.
    => 2 VUSA fills + 1 VOOL fill.
    """
    book = _make_book()
    vusa_bundle = _StepWeightBundle(_FIGI_VUSA, 0.5)
    vool_bundle = _StepWeightBundle(_FIGI_VOOL, 0.5)

    vusa_instr = _make_instrument(_FIGI_VUSA, VENUE_LSE)
    vool_instr = _make_instrument(_FIGI_VOOL, VENUE_XETRA)

    # VUSA: days 0, 1, 2, 3
    vusa_bars = _make_bars(_FIGI_VUSA, VENUE_LSE, [100.0, 101.0, 102.0, 103.0])

    # VOOL: days 0, 1, 3 (day 2 missing = XETR closed)
    vool_bars = _make_bars(_FIGI_VOOL, VENUE_XETRA, [200.0, 201.0], start_day=0)
    vool_bars += _make_bars(_FIGI_VOOL, VENUE_XETRA, [202.0], start_day=3)

    # Merge and sort by timestamp
    all_bars = sorted(vusa_bars + vool_bars, key=lambda b: b.ts_event)

    engine = BacktestEngine(BacktestEngineConfig(
        trader_id=TraderId("CADENCE-E2E"),
        logging=None,
    ))
    # MARGIN venues: the two fully-budgeted sleeves run a gross-2.0 book whose
    # stepping targets buy then add, which a CASH account would cash-constrain.
    # This test exercises calendar-awareness, not cash management.
    engine.add_venue(
        VENUE_LSE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_venue(
        VENUE_XETRA,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(vusa_instr)
    engine.add_instrument(vool_instr)
    engine.add_data(all_bars)

    config = RebalanceStrategyConfig(book=book)
    strategy = RebalanceStrategy(config=config)
    strategy.register_sleeve(book.sleeves[0].name, vusa_bundle)
    strategy.register_sleeve(book.sleeves[1].name, vool_bundle)
    # Inject a stub bimap (each FIGI → its venue-native InstrumentId) so the
    # strategy skips real OpenFIGI resolution.
    strategy._figi_bimap = {
        _FIGI_VUSA: InstrumentId.from_str(f"{_FIGI_VUSA}.{VENUE_LSE.value}"),
        _FIGI_VOOL: InstrumentId.from_str(f"{_FIGI_VOOL}.{VENUE_XETRA.value}"),
    }
    engine.add_strategy(strategy)

    engine.run()

    assert engine.get_result() is not None

    fills = [o for o in engine.cache.orders() if o.is_closed]
    # Should have:
    #   1. Period 1 rebalance (day 2 close): VUSA + VOOL
    #   2. Period 2 rebalance (day 3 close): VUSA only  (VOOL venue closed)
    # = 3 total fills
    assert len(fills) == 3, (
        f"Expected 3 fills (2 VUSA + 1 VOOL), got {len(fills)}: "
        f"{[(f.instrument_id.value, f.is_buy, float(f.quantity.as_double())) for f in fills]}"
    )

    vusa_fills = [f for f in fills if f.instrument_id == vusa_instr.id]
    vool_fills = [f for f in fills if f.instrument_id == vool_instr.id]

    assert len(vusa_fills) == 2, (
        f"VUSA should have 2 fills (day 2 + day 3), got {len(vusa_fills)}"
    )
    assert len(vool_fills) == 1, (
        f"VOOL should have 1 fill (day 2 only, day 3 skipped — XETR closed), "
        f"got {len(vool_fills)}"
    )

    for f in vusa_fills:
        assert f.is_buy, f"VUSA should be BUY, got {f}"
        assert float(f.quantity.as_double()) > 0

    for f in vool_fills:
        assert f.is_buy, f"VOOL should be BUY, got {f}"
        assert float(f.quantity.as_double()) > 0

    engine.dispose()
