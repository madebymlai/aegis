"""E2E regression for the identity linchpin (Wave A / aegis-rd-bwb.1, finding c1).

The FIGI→InstrumentId bimap (Security Master, Slice 3) must be the SINGLE source
of truth for instrument identity: the strategy subscribes, buffers, sizes, and
orders on the *resolved* InstrumentId — NOT on a naive ``f"{figi}.{venue}"``.

This is proven by making the resolved ticker DIFFERENT from the FIGI: the
instrument and its bars live under ``VUSA.XLON`` while the FIGI is the opaque
``BBG...`` string.  Before the fix the strategy subscribed to ``BBG....XLON``
(which has no instrument/bars) and never traded; after the fix it follows the
bimap to ``VUSA.XLON`` and fills.

N.B. all e2e use ``logging=None``; one BacktestEngine per test.
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

# FIGI and venue-native ticker are DELIBERATELY different.
_FIGI = "BBG000B9XRY4"
_TICKER = "VUSA"
VENUE = Venue("XLON")
_RESOLVED = InstrumentId.from_str(f"{_TICKER}.{VENUE.value}")  # VUSA.XLON ≠ BBG....XLON


class _SyntheticBundle(ExecutionBundle):
    def __init__(self, weight: float = 0.5) -> None:
        self._weight = weight
        contract = DataContract(
            figis=(_FIGI,),
            required_arrays=("Close",),
            base_currency="EUR",
            required_fx_currencies=(),
            timeframe="1D",
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="id-synth-001", role="synth", candidate_key="synth-key",
            component_source_hashes={}, figis=(_FIGI,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy", component_id="synth_strat", module="synth",
                input_names=(), output_names=(), params={},
            ),
            indicators=(), gross_cap=1.0, net_cap=None, direction="both",
            symbols=(_FIGI,), currency_by_symbol={_FIGI: "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self, prices: MarketDataBundle, *, fx_series=None,
    ) -> pd.DataFrame:
        close = prices.array("Close")
        df = pd.DataFrame({_FIGI: [self._weight] * len(close)}, index=close.index)
        df.columns.name = "figi"
        return df


def _make_instrument() -> Instrument:
    # The instrument lives under the resolved TICKER, not the FIGI.
    return eur_equity(_TICKER, VENUE.value)


def _make_bars(prices: list[float]) -> list[Bar]:
    instrument = _make_instrument()
    bar_type = BarType.from_str(f"{instrument.id.value}-1-DAY-LAST-EXTERNAL")
    interval_ns = 86_400_000_000_000
    bars: list[Bar] = []
    ts = 0
    for px in prices:
        p = instrument.make_price(px)
        bars.append(Bar(
            bar_type=bar_type, open=p, high=p, low=p, close=p,
            volume=instrument.make_qty(1000), ts_event=ts, ts_init=ts,
        ))
        ts += interval_ns
    return bars


def _make_book() -> BookConfig:
    return BookConfig(
        sleeves=(SleeveConfig(
            name=SleeveName("tracer"), wheel_filename="tracer.whl", budget=1.0,
        ),),
        base_currency="EUR",
        default_venue=VENUE.value,
    )


def test_strategy_follows_resolved_instrument_id():
    """The strategy must trade the bimap's resolved InstrumentId (VUSA.XLON),
    not a FIGI-shaped id (BBG....XLON) — proving Slice 3 is live, not dead."""
    instrument = _make_instrument()
    bars = _make_bars([100.0, 101.0, 102.0, 103.0, 104.0])

    engine = BacktestEngine(BacktestEngineConfig(
        trader_id=TraderId("IDENTITY-E2E"), logging=None,
    ))
    engine.add_venue(
        VENUE, oms_type=OmsType.NETTING, account_type=AccountType.CASH,
        base_currency=Currency.from_str("EUR"),
        starting_balances=[Money(100_000, Currency.from_str("EUR"))],
        book_type=BookType.L1_MBP,
    )
    engine.add_instrument(instrument)
    engine.add_data(bars)

    config = RebalanceStrategyConfig(book=_make_book())
    strategy = RebalanceStrategy(config=config)
    strategy.register_sleeve(
        _make_book().sleeves[0].name, _SyntheticBundle(weight=0.5)
    )
    # Bimap resolves the FIGI to a DIFFERENT id than f"{figi}.{venue}".
    strategy._figi_bimap = {_FIGI: _RESOLVED}
    engine.add_strategy(strategy)

    engine.run()

    fills = [o for o in engine.cache.orders() if o.is_closed]
    assert len(fills) == 1, (
        f"Expected 1 fill on the resolved id (trade to target, then hold); "
        f"got {len(fills)} (strategy likely subscribed to a FIGI-shaped id)"
    )
    for f in fills:
        assert f.instrument_id == _RESOLVED, (
            f"Fill must be on resolved {_RESOLVED}, got {f.instrument_id}"
        )
        assert f.is_buy

    engine.dispose()
