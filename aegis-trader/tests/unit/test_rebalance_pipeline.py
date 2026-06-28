"""Unit tests for the Strategy-free RebalancePipeline."""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
)
from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import OrderSide, SleeveName
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    GateOutcome,
    RebalancePipeline,
    StartupGate,
)

_INSTRUMENT_ID = InstrumentId.from_str("PIPE.XNYS")
_ES = InstrumentId.from_str("ES.XCME")  # synthetic continuous-root id (root "ES")
_SLEEVE = SleeveName("trend")
_DAY_NS = 86_400_000_000_000


class _FixedWeightBundle(ExecutionBundle):
    def __init__(self, weight: float) -> None:
        self._weight = weight
        contract = DataContract(
            instrument_ids=(_INSTRUMENT_ID,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="pipeline-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            instrument_ids=(_INSTRUMENT_ID,),
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
            instrument_bands={_INSTRUMENT_ID: DriftBand.symmetric(0.0)},
            gross_cap=1.0,
            net_cap=None,
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle) -> pd.DataFrame:
        close = prices.array("Close")
        target = pd.DataFrame(
            {_INSTRUMENT_ID: [self._weight, self._weight]},
            index=close.index,
        )
        target.columns.name = "instrument_id"
        return target


class _ContinuousWeightBundle(ExecutionBundle):
    """A futures-only sleeve: it declares a bare root and signals on the continuous-root id."""

    def __init__(self, weight: float) -> None:
        self._weight = weight
        contract = DataContract(
            instrument_ids=(_ES,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            lookback_bars=1,
            futures=("ES",),
        )
        manifest = BundleManifest(
            run_id="pipeline-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            instrument_ids=(_ES,),
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
            instrument_bands={_ES: DriftBand.symmetric(0.0)},
            gross_cap=1.0,
            net_cap=None,
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle) -> pd.DataFrame:
        close = prices.array("Close")
        target = pd.DataFrame({_ES: [self._weight, self._weight]}, index=close.index)
        target.columns.name = "instrument_id"
        return target


class _BookState:
    def __init__(
        self,
        realized_weights: dict[InstrumentId, float] | None = None,
        *,
        nav: float = 100_000.0,
        cash: float = 100_000.0,
        cache_healthy: bool = True,
    ) -> None:
        self._realized_weights = realized_weights or {}
        self._nav = nav
        self._cash = cash
        self._cache_healthy = cache_healthy

    def nav(self) -> float:
        return self._nav

    def cash(self) -> float:
        return self._cash

    def is_cache_healthy(self) -> bool:
        return self._cache_healthy

    def realized_weights(self) -> dict[InstrumentId, float]:
        return dict(self._realized_weights)


class _FailingNavBookState(_BookState):
    def nav(self) -> float:
        raise RuntimeError("portfolio offline")


class _MarketData:
    def __init__(
        self,
        bars_by_instrument_id: dict[InstrumentId, tuple[MarketBar, ...]] | None = None,
        fresh_instrument_ids: frozenset[InstrumentId] | None = None,
    ) -> None:
        self._bars_by_instrument_id = bars_by_instrument_id or _bars_by_instrument_id()
        self._fresh_instrument_ids = (
            frozenset({_INSTRUMENT_ID})
            if fresh_instrument_ids is None
            else fresh_instrument_ids
        )

    def instrument_sizing(self, _instrument_id: InstrumentId) -> InstrumentSizing:
        return InstrumentSizing(currency="EUR", size_increment=1.0)

    def make_quantity(self, _instrument_id: InstrumentId, raw_shares: float) -> float:
        return raw_shares

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        if base_currency == quote_currency:
            return 1.0
        return None

    def lookback_window(
        self,
        instrument_id: InstrumentId,
        _timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        _ = (period, period_ns)
        return self._bars_by_instrument_id.get(instrument_id, ())[-limit:]

    def has_bar_in_period(
        self,
        instrument_id: InstrumentId,
        _timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        _ = (period, period_ns)
        return instrument_id in self._fresh_instrument_ids


def _book(*, per_name_cap: float | None = None) -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(name=_SLEEVE, wheel_filename="trend.whl", risk_share=1.0),
        ),
        base_currency="EUR",
        per_name_cap=per_name_cap,
    )


def _bars_by_instrument_id() -> dict[InstrumentId, tuple[MarketBar, ...]]:
    return {
        _INSTRUMENT_ID: (
            MarketBar(0, 100.0, 100.0, 100.0, 100.0, 1_000.0),
            MarketBar(_DAY_NS, 100.0, 100.0, 100.0, 100.0, 1_000.0),
        )
    }


def _period() -> CompletedRebalancePeriod:
    return CompletedRebalancePeriod(period=1, period_ns=_DAY_NS)


def _pipeline(
    *,
    book_state: _BookState | None = None,
    market_data: _MarketData | None = None,
    book: BookConfig | None = None,
    bundle: ExecutionBundle | None = None,
) -> RebalancePipeline:
    return RebalancePipeline(
        book_state=book_state or _BookState(),
        market_data=market_data or _MarketData(),
        book=book or _book(),
        sleeve_to_bundle={_SLEEVE: bundle or _FixedWeightBundle(0.5)},
        ledger=SleeveLedger(),
    )


def test_rebalance_pipeline_returns_sized_orders_and_summary() -> None:
    result = _pipeline().rebalance_period(_period())

    assert result.orders[0].instrument_id == _INSTRUMENT_ID
    assert result.orders[0].side == OrderSide.BUY
    assert result.orders[0].quantity == 500.0
    assert result.summary.gate_outcome == GateOutcome.PASS
    assert result.summary.num_sleeves == 1
    assert result.summary.num_orders == 1


def test_rebalance_pipeline_targets_a_continuous_root_keyed_by_its_id() -> None:
    """E3: a continuous root is a first-class rebalance target (mirroring research's tradeable set
    = natives + continuous roots).  The pipeline reads its bars from the feed-backed series by the
    continuous id and produces an order keyed by it (root→front routing happens at submission)."""
    es_bars = {
        _ES: (
            MarketBar(0, 100.0, 100.0, 100.0, 100.0, 1_000.0),
            MarketBar(_DAY_NS, 100.0, 100.0, 100.0, 100.0, 1_000.0),
        )
    }
    market_data = _MarketData(
        bars_by_instrument_id=es_bars, fresh_instrument_ids=frozenset({_ES})
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=market_data,
        book=_book(),
        sleeve_to_bundle={_SLEEVE: _ContinuousWeightBundle(0.5)},
        ledger=SleeveLedger(),
        continuous_ids_by_root={"ES": _ES},
    )

    result = pipeline.rebalance_period(_period())

    assert result.orders[0].instrument_id == _ES
    assert result.orders[0].side == OrderSide.BUY


def test_rebalance_pipeline_filters_orders_when_market_data_reports_stale_instrument() -> None:
    result = _pipeline(
        market_data=_MarketData(fresh_instrument_ids=frozenset())
    ).rebalance_period(_period())

    assert result.orders == ()
    assert result.summary.num_targets == 1
    assert result.summary.num_orders == 0


def test_rebalance_pipeline_reports_gate_error_in_summary() -> None:
    result = _pipeline(
        book=_book(per_name_cap=0.5),
        book_state=_BookState({_INSTRUMENT_ID: 0.7}),
        bundle=_FixedWeightBundle(0.8),
    ).rebalance_period(_period())

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.ERROR
    assert result.halt_reason is not None
    assert "InstrumentId PIPE.XNYS" in result.halt_reason
    assert "unfixable" in result.halt_reason


def test_startup_check_passes_when_cap_and_integrity_gates_pass() -> None:
    result = _pipeline().startup_check()

    assert result.trading_enabled is True
    assert result.should_halt is False
    assert result.halt_gate is None
    assert result.halt_reason is None
    assert result.nav == 100_000.0
    assert result.cash == 100_000.0


def test_startup_check_halts_when_book_cap_exceeds_bundle_cap() -> None:
    result = _pipeline(book=_book(per_name_cap=1.5)).startup_check()

    assert result.should_halt is True
    assert result.halt_gate == StartupGate.CAP_PROVENANCE
    assert result.halt_reason == (
        "book per_name_cap (1.5) exceeds sleeve 'trend' bundle gross_cap (1.0)"
    )


def test_startup_check_halts_when_bundle_bands_overlap() -> None:
    trend = SleeveName("trend")
    carry = SleeveName("carry")
    book = BookConfig(
        sleeves=(
            SleeveConfig(name=trend, wheel_filename="trend.whl", risk_share=0.5),
            SleeveConfig(name=carry, wheel_filename="carry.whl", risk_share=0.5),
        ),
        base_currency="EUR",
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=book,
        sleeve_to_bundle={
            trend: _FixedWeightBundle(0.5),
            carry: _FixedWeightBundle(0.5),
        },
        ledger=SleeveLedger(),
    )

    result = pipeline.startup_check()

    assert result.should_halt is True
    assert result.halt_gate == StartupGate.BAND_OWNERSHIP
    assert result.halt_reason is not None
    assert "PIPE.XNYS" in result.halt_reason
    assert "carry" in result.halt_reason
    assert "trend" in result.halt_reason


def test_startup_check_halts_when_book_state_query_fails() -> None:
    result = _pipeline(book_state=_FailingNavBookState()).startup_check()

    assert result.should_halt is True
    assert result.halt_gate == StartupGate.ACCOUNT_INTEGRITY
    assert result.halt_reason == (
        "Failed to query book state for integrity check: portfolio offline"
    )


def test_startup_check_halts_when_account_integrity_fails() -> None:
    result = _pipeline(
        book_state=_BookState(nav=100_000.0, cash=90_000.0)
    ).startup_check()

    assert result.should_halt is True
    assert result.halt_gate == StartupGate.ACCOUNT_INTEGRITY
    assert result.halt_reason == (
        "NAV/cash mismatch: NAV=100000.00, cash=90000.00, "
        "gap=10000.00 exceeds tolerance 0.00 (fraction=0.0)"
    )
