"""Quote-driven fills end to end (aegis-rd-tggo.5).

A quote-marked leg's BID + ASK bars are the single source: the simulated venue
pairs them into L1 quotes and fills market orders at the real touch, the
Portfolio marks the position at the fed quote mid, and no fill-cost parameter
exists — the crossing cost falls out of the observed spread.  The book-global
``slippage_probability`` is deliberately set to 1.0 to prove it no longer
drives a quote-marked leg's fill.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity

from aegis_data.marking import DeclaredMarkingResolver, MarkMode
from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
    MissingIndexPolicy,
)
from aegis_runtime.currency import CurrencyConversion

from aegis_trader.backtest import BacktestMarketData, run_book_backtest
from aegis_trader.bundles.stub import StubBundleRegistry
from aegis_trader.portfolio.performance import BookEquityRecorder

_TIGHT = InstrumentId.from_str("TIGHT.XETR")
_WIDE = InstrumentId.from_str("WIDE.XETR")
_WHEEL = "quote-fills.whl"
_STARTING_CASH = 1_000_000.0

# Constant quotes so the touch is unambiguous on every day: the tight leg
# crosses a 0.10 spread, the wide leg a 1.00 spread, around the same mid shape.
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


class _TwoLegFixedWeightBundle(ExecutionBundle):
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
            gross_cap=1.0,
            net_cap=None,
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
            ohlcv={
                _TIGHT: (tight_bid + tight_ask) / 2.0,
                _WIDE: (wide_bid + wide_ask) / 2.0,
            },
            quote_frames={
                _TIGHT: (tight_bid, tight_ask),
                _WIDE: (wide_bid, wide_ask),
            },
        )


def test_quote_marked_legs_fill_at_the_touch_and_mark_at_the_mid(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    registry = StubBundleRegistry({_WHEEL: _TwoLegFixedWeightBundle()})
    resolver = DeclaredMarkingResolver(
        declared={_TIGHT: MarkMode.QUOTE, _WIDE: MarkMode.QUOTE}
    )

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        registry=registry,
        data_source=_QuoteMarkedDataSource(),
        bar_type_resolver=resolver,
    )
    engine = result.engine

    try:
        fills = {
            order.instrument_id: order
            for order in engine.cache.orders()
            if order.is_closed
        }
        # Dense quotes with NO trade series: both legs fill.
        assert set(fills) == {_TIGHT, _WIDE}
        # The fill IS the real touch — buy at the ask, exactly, even though the
        # book-global slippage_probability is 1.0 (retired for quote venues).
        assert fills[_TIGHT].avg_px == pytest.approx(_TIGHT_ASK)
        assert fills[_WIDE].avg_px == pytest.approx(_WIDE_ASK)
        # Each leg pays its own observed spread: wide costs 10x tight per share.
        tight_cost = fills[_TIGHT].avg_px - _mid(_TIGHT_BID, _TIGHT_ASK)
        wide_cost = fills[_WIDE].avg_px - _mid(_WIDE_BID, _WIDE_ASK)
        assert wide_cost == pytest.approx(10.0 * tight_cost)
        # The book marks open positions at the quote mid (the single
        # reference_price formula), not at the bid/touch: final equity equals
        # cash after the ask fills plus the positions valued at mid.
        tight_qty = fills[_TIGHT].quantity.as_double()
        wide_qty = fills[_WIDE].quantity.as_double()
        expected_equity = (
            _STARTING_CASH
            - tight_qty * (_TIGHT_ASK - _mid(_TIGHT_BID, _TIGHT_ASK))
            - wide_qty * (_WIDE_ASK - _mid(_WIDE_BID, _WIDE_ASK))
        )
        assert _final_equity(engine) == pytest.approx(expected_equity, abs=1.0)
    finally:
        engine.dispose()


def _mid(bid: float, ask: float) -> float:
    return (bid + ask) / 2.0


def _final_equity(engine: Any) -> float:
    for actor in engine.trader.actors():
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
