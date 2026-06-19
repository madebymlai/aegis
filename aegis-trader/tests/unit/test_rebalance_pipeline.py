"""Unit tests for the Nautilus-free RebalancePipeline."""

from __future__ import annotations

from datetime import date

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    FuturesRef,
    ListedRef,
    LockedExecutionPlan,
    MarketDataBundle,
)

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import OrderSide, SleeveName
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    FixtureInstrumentResolver,
    GateOutcome,
    MarketBar,
    RebalancePipeline,
    StartupGate,
)

_FIGI = ListedRef("BBG000PIPE01")
_FUT = FuturesRef("ES", "cme")
_INSTRUMENT_ID = InstrumentId.from_str("PIPE.XNYS")
_FRONT_ID = InstrumentId.from_str("ESZ4.XCME")
_NEXT_ID = InstrumentId.from_str("ESH5.XCME")
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


class _FuturesBundle(ExecutionBundle):
    def __init__(self) -> None:
        contract = DataContract(
            refs=(_FUT,),
            required_arrays=("Close",),
            base_currency="EUR",
            required_fx_currencies=(),
            timeframe="1D",
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="pipeline-futures-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            refs=(_FUT,),
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
            symbols=("ES",),
            currency_by_symbol={"ES": "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)


class _MixedRefBundle(ExecutionBundle):
    def __init__(self) -> None:
        contract = DataContract(
            refs=(_FIGI, _FUT),
            required_arrays=("Close",),
            base_currency="EUR",
            required_fx_currencies=(),
            timeframe="1D",
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="pipeline-mixed-ref-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            refs=(_FIGI, _FUT),
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
            symbols=(_FIGI.value, "ES"),
            currency_by_symbol={_FIGI.value: "EUR", "ES": "EUR"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)


class _BookState:
    def __init__(
        self,
        realized_weights: dict[ListedRef, float] | None = None,
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

    def realized_weights(self) -> dict[ListedRef, float]:
        return dict(self._realized_weights)


class _MarketData:
    def __init__(
        self,
        bars_by_ref: dict[object, tuple[MarketBar, ...]] | None = None,
        fresh_refs: frozenset[object] | None = None,
    ) -> None:
        self._bars_by_ref = bars_by_ref or _bars_by_ref()
        self._fresh_refs = frozenset({_FIGI}) if fresh_refs is None else fresh_refs

    def instrument_sizing(self, _instrument_id: object) -> InstrumentSizing:
        return InstrumentSizing(currency="EUR", size_increment=1.0)

    def make_quantity(self, _instrument_id: object, raw_shares: float) -> float:
        return raw_shares

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        if base_currency == quote_currency:
            return 1.0
        return None

    def lookback_window(
        self,
        ref: object,
        _instrument_id: object,
        _timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        _ = (period, period_ns)
        return self._bars_by_ref.get(ref, ())[-limit:]

    def has_bar_in_period(
        self,
        ref: object,
        _instrument_id: object,
        _timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        _ = (period, period_ns)
        return ref in self._fresh_refs


def _book(*, per_name_cap: float | None = None) -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(name=_SLEEVE, wheel_filename="trend.whl", risk_share=1.0),
        ),
        base_currency="EUR",
        per_name_cap=per_name_cap,
    )


def _bars_by_ref() -> dict[object, tuple[MarketBar, ...]]:
    return {
        _FIGI: (
            MarketBar(
                ts_event=0,
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1_000.0,
            ),
            MarketBar(
                ts_event=86_400_000_000_000,
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=1_000.0,
            ),
        )
    }


def _period() -> CompletedRebalancePeriod:
    return CompletedRebalancePeriod(period=1, period_ns=86_400_000_000_000)


def test_rebalance_pipeline_returns_sized_orders_and_summary() -> None:
    book = _book()
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=book,
        sleeve_to_bundle={_SLEEVE: _FixedWeightBundle(0.5)},
        ledger=SleeveLedger(),
        resolve_instrument=FixtureInstrumentResolver({_FIGI: _INSTRUMENT_ID}),
    )
    pipeline.initialize_identity(pd.Timestamp("2026-01-01").date())

    result = pipeline.rebalance_period(_period())

    assert result.orders[0].ref == _FIGI
    assert result.orders[0].side == OrderSide.BUY
    assert result.orders[0].quantity == 500.0
    assert result.summary.gate_outcome == GateOutcome.PASS
    assert result.summary.num_sleeves == 1
    assert result.summary.num_orders == 1


def test_rebalance_pipeline_filters_orders_when_market_data_reports_stale_ref() -> None:
    book = _book()
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(fresh_refs=frozenset()),
        book=book,
        sleeve_to_bundle={_SLEEVE: _FixedWeightBundle(0.5)},
        ledger=SleeveLedger(),
        resolve_instrument=FixtureInstrumentResolver({_FIGI: _INSTRUMENT_ID}),
    )
    pipeline.initialize_identity(pd.Timestamp("2026-01-01").date())

    result = pipeline.rebalance_period(_period())

    assert result.orders == ()
    assert result.summary.num_targets == 1
    assert result.summary.num_orders == 0


def test_pipeline_initializes_mixed_ref_identity() -> None:
    resolver = FixtureInstrumentResolver({_FIGI: _INSTRUMENT_ID, _FUT: _FRONT_ID})
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=_book(),
        sleeve_to_bundle={_SLEEVE: _MixedRefBundle()},
        ledger=SleeveLedger(),
        resolve_instrument=resolver,
    )

    pipeline.initialize_identity(date(2026, 6, 11))

    identity = pipeline.resolved_identity_snapshot()
    assert identity == {_FUT: _FRONT_ID, _FIGI: _INSTRUMENT_ID}
    assert pipeline.ref_for_instrument_value(_FRONT_ID.value) == _FUT
    assert pipeline.ref_for_instrument_value(_INSTRUMENT_ID.value) == _FIGI


def test_pipeline_refresh_keeps_old_contract_inverse_for_roll() -> None:
    def resolver(_ref: object, as_of: date) -> InstrumentId:
        if as_of < date(2026, 6, 12):
            return _FRONT_ID
        return _NEXT_ID

    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=_book(),
        sleeve_to_bundle={_SLEEVE: _FuturesBundle()},
        ledger=SleeveLedger(),
        resolve_instrument=resolver,
    )

    pipeline.initialize_identity(date(2026, 6, 11))
    changes = pipeline.refresh_resolution(date(2026, 6, 12))
    roll_contract_id = pipeline.resolve_contract_id_for_roll(_FUT, date(2026, 6, 12))

    assert changes[0].previous == _FRONT_ID
    assert changes[0].current == _NEXT_ID
    assert pipeline.instrument_id_for_ref(_FUT) == _NEXT_ID
    assert pipeline.ref_for_instrument_value(_FRONT_ID.value) == _FUT
    assert pipeline.ref_for_instrument_value(_NEXT_ID.value) == _FUT
    assert roll_contract_id.value == _NEXT_ID.value


def test_rebalance_pipeline_reports_gate_error_in_summary() -> None:
    book = _book(per_name_cap=0.5)
    pipeline = RebalancePipeline(
        book_state=_BookState({_FIGI: 0.7}),
        market_data=_MarketData(),
        book=book,
        sleeve_to_bundle={_SLEEVE: _FixedWeightBundle(0.8)},
        ledger=SleeveLedger(),
        resolve_instrument=FixtureInstrumentResolver({_FIGI: _INSTRUMENT_ID}),
    )
    pipeline.initialize_identity(pd.Timestamp("2026-01-01").date())

    result = pipeline.rebalance_period(_period())

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.ERROR
    assert result.halt_reason == (
        "FIGI BBG000PIPE01: target weight 0.800000 exceeds per-name cap 0.500000 — unfixable"
    )


def test_startup_check_halts_when_book_cap_exceeds_bundle_cap() -> None:
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=_book(per_name_cap=1.5),
        sleeve_to_bundle={_SLEEVE: _FixedWeightBundle(0.5)},
        ledger=SleeveLedger(),
        resolve_instrument=FixtureInstrumentResolver({_FIGI: _INSTRUMENT_ID}),
    )

    result = pipeline.startup_check()

    assert result.should_halt is True
    assert result.halt_gate == StartupGate.CAP_PROVENANCE
    assert result.halt_reason == (
        "book per_name_cap (1.5) exceeds sleeve 'trend' bundle gross_cap (1.0)"
    )


def test_startup_check_halts_when_account_integrity_fails() -> None:
    pipeline = RebalancePipeline(
        book_state=_BookState(nav=100_000.0, cash=90_000.0),
        market_data=_MarketData(),
        book=_book(),
        sleeve_to_bundle={_SLEEVE: _FixedWeightBundle(0.5)},
        ledger=SleeveLedger(),
        resolve_instrument=FixtureInstrumentResolver({_FIGI: _INSTRUMENT_ID}),
    )

    result = pipeline.startup_check()

    assert result.should_halt is True
    assert result.halt_gate == StartupGate.ACCOUNT_INTEGRITY
    assert result.halt_reason == (
        "NAV/cash mismatch: NAV=100000.00, cash=90000.00, "
        "gap=10000.00 exceeds tolerance 0.00 (fraction=0.0)"
    )
