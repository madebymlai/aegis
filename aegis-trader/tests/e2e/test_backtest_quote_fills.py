"""Quote-driven fills end to end (aegis-rd-tggo.5).

A quote-marked leg's BID + ASK bars are the single source: the simulated venue
pairs them into L1 quotes and fills market orders at the real touch, the
Portfolio marks the position at the strategy-published quote mid, and no
fill-cost parameter exists — the crossing cost falls out of the observed
spread.  The book-global ``slippage_probability`` is deliberately set to 1.0
to prove it no longer drives a quote-marked leg's fill.

One deterministic backtest (fixed weights over constant quotes) is run once;
each test asserts a single literal outcome of it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    LockedExecutionPlan,
    MarketDataBundle,
    MissingIndexPolicy,
)
from aegis_runtime.domain.currency import CurrencyConversion

from aegis_data.marking import MarkMode
from aegis_trader.backtest import BacktestMarketData, run_book_backtest
from aegis_trader.portfolio.performance import BookEquityRecorder
from tests.support.bundle_double import BundleDouble, make_bundle_registry
from tests.support.market_data import bar_window_from_frames

_TIGHT = InstrumentId.from_str("TIGHT.XETR")
_WIDE = InstrumentId.from_str("WIDE.XETR")
_WHEEL = "quote-fills.whl"

# Constant quotes so the touch is unambiguous on every day: the tight leg
# crosses a 0.10 spread, the wide leg a 1.00 spread.
_TIGHT_BID, _TIGHT_ASK = 100.00, 100.10
_WIDE_BID, _WIDE_ASK = 100.00, 101.00

_BOOK_TOML = f"""
base_currency = "EUR"

[costs]
slippage_probability = 1.0

[[sleeves]]
name = "carry"
wheel_filename = "{_WHEEL}"
risk_share = 1.0
group = "Floor"
"""


@dataclass(frozen=True)
class _QuoteFillOutcome:
    """The finished run's observable facts, one field per test."""

    filled_instrument_ids: frozenset[InstrumentId]
    tight_fill_price: float
    wide_fill_price: float
    final_equity: float


@pytest.fixture(scope="module")
def outcome(tmp_path_factory: pytest.TempPathFactory) -> _QuoteFillOutcome:
    book_path = tmp_path_factory.mktemp("quote-fills") / "book.toml"
    book_path.write_text(_BOOK_TOML)
    registry = make_bundle_registry({_WHEEL: _TwoLegFixedWeightBundle()})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        registry=registry,
        data_source=_QuoteMarkedDataSource(),
    )
    engine = result.engine

    try:
        fills = {
            order.instrument_id: order
            for order in engine.cache.orders()
            if order.is_closed
        }
        return _QuoteFillOutcome(
            filled_instrument_ids=frozenset(fills),
            tight_fill_price=fills[_TIGHT].avg_px,
            wide_fill_price=fills[_WIDE].avg_px,
            final_equity=_final_equity(engine),
        )
    finally:
        engine.dispose()


def test_quote_marked_legs_fill_from_dense_quotes_with_no_trade_series(
    outcome: _QuoteFillOutcome,
) -> None:
    assert outcome.filled_instrument_ids == {_TIGHT, _WIDE}


def test_a_buy_fills_exactly_at_the_ask_despite_certain_global_slippage(
    outcome: _QuoteFillOutcome,
) -> None:
    # slippage_probability is 1.0 in the book config; the quote venue retires it.
    assert outcome.tight_fill_price == pytest.approx(100.10)


def test_a_wide_leg_pays_its_own_observed_spread_not_a_shared_knob(
    outcome: _QuoteFillOutcome,
) -> None:
    assert outcome.wide_fill_price == pytest.approx(101.00)


def test_open_positions_mark_at_the_quote_mid_not_the_touch(
    outcome: _QuoteFillOutcome,
) -> None:
    # 1_000_000 - 2499 shares x 0.05 tight half-spread - 2488 shares x 0.50
    # wide half-spread: equity at mid to the cent.  Marked at the bid instead,
    # equity would read 997_262.05 (a further half-spread per share lower).
    assert outcome.final_equity == pytest.approx(998_631.05, abs=0.01)


class _TwoLegFixedWeightBundle(BundleDouble):
    """Synthetic bundle holding both quote-marked legs at a fixed weight."""

    def __init__(self) -> None:
        self._instrument_ids = (_TIGHT, _WIDE)
        contract = DataContract(
            instrument_ids=self._instrument_ids,
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            # As a real export records it: both legs quote-marked, so the
            # runner resolves the same recorded view live would consume.
            mark_modes={_TIGHT: "QUOTE", _WIDE: "QUOTE"},
        )
        manifest = BundleManifest(
            run_id="quote-fills-synth",
            role="synth",
            candidate_key="quote-fills-synth-key",
            component_source_hashes={},
            instrument_ids=self._instrument_ids,
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="fixed_weight_quote_legs",
                module="synth",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={
                instrument_id: DriftBand.symmetric(0.02)
                for instrument_id in self._instrument_ids
            },
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        weights = pd.DataFrame(
            {_TIGHT: [0.25] * len(close), _WIDE: [0.25] * len(close)},
            index=close.index,
        )
        weights.columns.name = "instrument_id"
        return weights


class _QuoteMarkedDataSource:
    """Data source serving ONLY sided quotes for both legs — no LAST series
    exists anywhere, exactly the thin-ETF corpus shape."""

    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> BacktestMarketData:
        tight_bid = _flat_frame(_TIGHT_BID)
        tight_ask = _flat_frame(_TIGHT_ASK)
        wide_bid = _flat_frame(_WIDE_BID)
        wide_ask = _flat_frame(_WIDE_ASK)
        return BacktestMarketData(
            instruments={_TIGHT: _equity(_TIGHT), _WIDE: _equity(_WIDE)},
            bar_windows={
                _TIGHT: bar_window_from_frames(
                    _TIGHT,
                    "1D",
                    MarkMode.QUOTE,
                    (tight_bid, tight_ask),
                ),
                _WIDE: bar_window_from_frames(
                    _WIDE,
                    "1D",
                    MarkMode.QUOTE,
                    (wide_bid, wide_ask),
                ),
            },
        )


def _final_equity(engine: object) -> float:
    for actor in engine.trader.actors():  # type: ignore[attr-defined]
        if isinstance(actor, BookEquityRecorder):
            return float(actor.equity_curve.iloc[-1])
    raise AssertionError("no BookEquityRecorder on the engine")


def _flat_frame(price: float) -> pd.DataFrame:
    days = pd.date_range("2020-01-01", periods=4, freq="D")
    return pd.DataFrame(
        {
            "Open": [price] * len(days),
            "High": [price] * len(days),
            "Low": [price] * len(days),
            "Close": [price] * len(days),
            "Volume": [1_000_000.0] * len(days),
        },
        index=days,
    )


def _equity(instrument_id: InstrumentId) -> Equity:
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        currency=Currency.from_str("EUR"),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )
