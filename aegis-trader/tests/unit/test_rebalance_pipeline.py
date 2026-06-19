"""Unit tests for the Nautilus-free RebalancePipeline."""

from __future__ import annotations

import pandas as pd

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    ListedRef,
    LockedExecutionPlan,
    MarketDataBundle,
)

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import OrderSide, SleeveName
from aegis_trader.observability.port import GateOutcome
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    MarketBar,
    RebalancePipeline,
)

_FIGI = ListedRef("BBG000PIPE01")
_SLEEVE = SleeveName("trend")


class _FixedWeightBundle(ExecutionBundle):
    def __init__(self, weight: float) -> None:
        self._weight = weight
        contract = DataContract(
            refs=(_FIGI,),
            required_arrays=("Close",),
            base_currency="EUR",
            required_fx_currencies=(),
            timeframe="1D",
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="pipeline-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            refs=(_FIGI,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="fixed",
                module="tests.fixed",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            gross_cap=1.0,
            net_cap=None,
            direction="both",
            symbols=(_FIGI.value,),
            currency_by_symbol={_FIGI.value: "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self, prices: MarketDataBundle, *, fx_series=None
    ) -> pd.DataFrame:
        close = prices.array("Close")
        target = pd.DataFrame({_FIGI: [self._weight, self._weight]}, index=close.index)
        target.columns.name = "figi"
        return target


class _BookState:
    def __init__(self, realized_weights: dict[ListedRef, float] | None = None) -> None:
        self._realized_weights = realized_weights or {}

    def nav(self) -> float:
        return 100_000.0

    def cash(self) -> float:
        return 100_000.0

    def is_cache_healthy(self) -> bool:
        return True

    def realized_weights(self) -> dict[ListedRef, float]:
        return dict(self._realized_weights)


class _MarketData:
    def instrument_sizing(self, _instrument_id: object) -> InstrumentSizing:
        return InstrumentSizing(currency="EUR", size_increment=1.0)

    def make_quantity(self, _instrument_id: object, raw_shares: float) -> float:
        return raw_shares

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        if base_currency == quote_currency:
            return 1.0
        return None


def _book(*, per_name_cap: float | None = None) -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(name=_SLEEVE, wheel_filename="trend.whl", risk_share=1.0),
        ),
        base_currency="EUR",
        per_name_cap=per_name_cap,
    )


def _period() -> CompletedRebalancePeriod:
    return CompletedRebalancePeriod(
        bars_by_ref={
            _FIGI: (
                MarketBar(ts_event=0, open=100.0, high=100.0, low=100.0, close=100.0, volume=1_000.0),
                MarketBar(ts_event=86_400_000_000_000, open=100.0, high=100.0, low=100.0, close=100.0, volume=1_000.0),
            )
        },
        fresh_refs=frozenset({_FIGI}),
    )


def test_rebalance_pipeline_returns_sized_orders_and_summary() -> None:
    book = _book()
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=book,
        sleeve_to_bundle={_SLEEVE: _FixedWeightBundle(0.5)},
        ledger=SleeveLedger(),
        resolve_instrument=lambda ref: ref.value,
    )

    result = pipeline.rebalance_period(_period())

    assert result.orders[0].ref == _FIGI
    assert result.orders[0].side == OrderSide.BUY
    assert result.orders[0].quantity == 500.0
    assert result.summary.gate_outcome == GateOutcome.PASS
    assert result.summary.num_sleeves == 1
    assert result.summary.num_orders == 1


def test_rebalance_pipeline_reports_gate_error_in_summary() -> None:
    book = _book(per_name_cap=0.5)
    pipeline = RebalancePipeline(
        book_state=_BookState({_FIGI: 0.7}),
        market_data=_MarketData(),
        book=book,
        sleeve_to_bundle={_SLEEVE: _FixedWeightBundle(0.8)},
        ledger=SleeveLedger(),
        resolve_instrument=lambda ref: ref.value,
    )

    result = pipeline.rebalance_period(_period())

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.ERROR
    assert result.halt_reason == (
        "FIGI BBG000PIPE01: target weight 0.800000 exceeds per-name cap 0.500000 — unfixable"
    )
