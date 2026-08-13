"""Unit tests for the Strategy-free RebalancePipeline."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.custom_data import (
    CustomDataProviderPort,
    ProviderAnswer,
)
from aegis_data.storage import Catalog
from aegis_runtime.domain.rebasing import ratio_rebasing, spread_rebasing
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
from aegis_runtime.domain.currency import CurrencyConversion

from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.roll import RollEvent
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.analytics_horizon import derive_horizon
from aegis_trader.domain.sleeve_ledger import BookObservation, SleeveLedger
from aegis_trader.domain.startup import StartupGate
from aegis_trader.domain.types import OrderSide, SleeveName
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    DueSleeve,
    GateOutcome,
    RebalancePipeline,
    RebalanceRequest,
)
from aegis_trader.trader.sleeve_arrays import SleeveArrays
from tests.support.factories import assemble_test_book
from tests.support.custom_data import FixtureRecord

_INSTRUMENT_ID = InstrumentId.from_str("PIPE.XNYS")
_ES = InstrumentId.from_str("ES.XCME")  # synthetic continuous-root id (root "ES")
_LSE_LEG = InstrumentId.from_str("AAA.XLON")
_BRU_LEG = InstrumentId.from_str("BBB.XBRU")
_SLEEVE = SleeveName("trend")
_DAY_NS = 86_400_000_000_000


class _FixedWeightBundle(ExecutionBundle):
    def __init__(self, weight: float, *, band: DriftBand | None = None) -> None:
        self._weight = weight
        instrument_band = band or DriftBand.symmetric(0.0)
        contract = DataContract(
            instrument_ids=(_INSTRUMENT_ID,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
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
            instrument_bands={_INSTRUMENT_ID: instrument_band},
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        target = pd.DataFrame(
            {_INSTRUMENT_ID: [self._weight, self._weight]},
            index=close.index,
        )
        target.columns.name = "instrument_id"
        return target


class _EmptyCustomProvider(CustomDataProviderPort[FixtureRecord]):
    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ProviderAnswer[FixtureRecord]:
        return ProviderAnswer((), start)


class _ContinuousWeightBundle(ExecutionBundle):
    """A futures-only sleeve: it declares a bare root and signals on the continuous-root id."""

    def __init__(self, weight: float) -> None:
        self._weight = weight
        contract = DataContract(
            instrument_ids=(_ES,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            futures=("ES",),
            adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
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
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        target = pd.DataFrame({_ES: [self._weight, self._weight]}, index=close.index)
        target.columns.name = "instrument_id"
        return target


class _CalendarParityBundle(ExecutionBundle):
    def __init__(
        self,
        *,
        missing_index: MissingIndexPolicy = MissingIndexPolicy.DROP,
        custom_arrays: bool = False,
    ) -> None:
        self.close_panel: pd.DataFrame | None = None
        self.fixture_panel: pd.DataFrame | None = None
        self.weights: pd.DataFrame | None = None
        contract = DataContract(
            instrument_ids=(_LSE_LEG, _BRU_LEG),
            required_arrays=(
                "Close",
                *(("FixtureValue", "FixtureAvailable") if custom_arrays else ()),
            ),
            base_currency="EUR",
            timeframe="1D",
            missing_index=missing_index,
            lookback_bars=2,
        )
        manifest = BundleManifest(
            run_id="pipeline-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            instrument_ids=(_LSE_LEG, _BRU_LEG),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="calendar-parity",
                module="tests.calendar_parity",
                input_names=("Close",),
                output_names=("target_weights",),
                params={},
            ),
            indicators=(),
            instrument_bands={
                _LSE_LEG: DriftBand.symmetric(0.0),
                _BRU_LEG: DriftBand.symmetric(0.0),
            },
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        self.close_panel = close.copy()
        if "FixtureValue" in self.contract.required_arrays:
            self.fixture_panel = native_prices.array("FixtureValue").copy()
        weights = close.div(close.sum(axis=1), axis=0)
        weights.columns.name = "instrument_id"
        self.weights = weights
        return weights


class _PoisonBundle(ExecutionBundle):
    """A sleeve whose compute blows up — the blast-radius probe for per-sleeve isolation."""

    def __init__(self) -> None:
        contract = DataContract(
            instrument_ids=(_LSE_LEG,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="pipeline-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            instrument_ids=(_LSE_LEG,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="poison",
                module="tests.poison",
                input_names=("Close",),
                output_names=("target_weights",),
                params={},
            ),
            indicators=(),
            instrument_bands={_LSE_LEG: DriftBand.symmetric(0.0)},
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        raise RuntimeError("component exploded")


class _PoisonFixedInstrumentBundle(_FixedWeightBundle):
    """A poison sleeve owning the fixed instrument's band (for the all-fail case)."""

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        raise RuntimeError("component exploded")


class _BandAccessFailsBundle(_FixedWeightBundle):
    @property
    def instrument_bands(self) -> Mapping[InstrumentId, DriftBand]:
        raise AssertionError("constructor must not read bundle drift bands")


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
        currencies: dict[InstrumentId, str] | None = None,
        pairs: dict[InstrumentId, tuple[str, str]] | None = None,
        fx_rates: dict[str, float] | None = None,
    ) -> None:
        self._bars_by_instrument_id = bars_by_instrument_id or _bars_by_instrument_id()
        self._fresh_instrument_ids = (
            frozenset({_INSTRUMENT_ID})
            if fresh_instrument_ids is None
            else fresh_instrument_ids
        )
        self._currencies = currencies or {}
        self._pairs = pairs or {}
        self._fx_rates = fx_rates or {}

    def instrument_sizing(self, instrument_id: InstrumentId) -> InstrumentSizing:
        return InstrumentSizing(
            currency=self._currencies.get(instrument_id, "EUR"), size_increment=1.0
        )

    def make_quantity(self, _instrument_id: InstrumentId, raw_shares: float) -> float:
        return raw_shares

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        return instrument_id

    def currency_pair(self, instrument_id: InstrumentId) -> tuple[str, str] | None:
        return self._pairs.get(instrument_id)

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        if base_currency == quote_currency:
            return 1.0
        return self._fx_rates.get(quote_currency)

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


def _book(
    *,
    per_name_cap: float | None = None,
    gross_cap: float = 1.0,
) -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(name=_SLEEVE, wheel_filename="trend.whl", risk_share=1.0),
        ),
        base_currency="EUR",
        per_name_cap=per_name_cap,
        gross_cap=gross_cap,
    )


def _bars_by_instrument_id() -> dict[InstrumentId, tuple[MarketBar, ...]]:
    return {
        _INSTRUMENT_ID: (
            MarketBar(0, 100.0, 100.0, 100.0, 100.0, 1_000.0),
            MarketBar(_DAY_NS, 100.0, 100.0, 100.0, 100.0, 1_000.0),
        )
    }


def _mixed_calendar_bars() -> dict[InstrumentId, tuple[MarketBar, ...]]:
    return {
        _LSE_LEG: (
            MarketBar(0, 10.0, 10.0, 10.0, 10.0, 1_000.0),
            MarketBar(_DAY_NS, 11.0, 11.0, 11.0, 11.0, 1_000.0),
            MarketBar(3 * _DAY_NS, 30.0, 30.0, 30.0, 30.0, 1_000.0),
            MarketBar(4 * _DAY_NS, 40.0, 40.0, 40.0, 40.0, 1_000.0),
        ),
        _BRU_LEG: (
            MarketBar(0, 12.0, 12.0, 12.0, 12.0, 1_000.0),
            MarketBar(_DAY_NS, 13.0, 13.0, 13.0, 13.0, 1_000.0),
            MarketBar(2 * _DAY_NS, 22.0, 22.0, 22.0, 22.0, 1_000.0),
            MarketBar(4 * _DAY_NS, 60.0, 60.0, 60.0, 60.0, 1_000.0),
        ),
    }


def _period() -> CompletedRebalancePeriod:
    return CompletedRebalancePeriod(period=1, period_ns=_DAY_NS)


def _all_due(*names: SleeveName) -> RebalanceRequest:
    period = _period()
    due_names = names or (_SLEEVE,)
    return RebalanceRequest(
        due=tuple(DueSleeve(sleeve=name, period=period) for name in due_names),
        timestamp_ns=3 * _DAY_NS,
    )


def _record_close(ledger: SleeveLedger, close: float, day: int) -> None:
    ledger.record(
        BookObservation(
            timestamp_ns=day * _DAY_NS,
            nav=100.0,
            realized_weights={_ES: 1.0},
            sleeve_targets={_SLEEVE: {_ES: 1.0}},
            marks={_ES: close},
        )
    )


def _pipeline(
    *,
    book_state: _BookState | None = None,
    market_data: _MarketData | None = None,
    book: BookConfig | None = None,
    bundle: ExecutionBundle | None = None,
    arrays: SleeveArrays | None = None,
) -> RebalancePipeline:
    config = book or _book()
    loaded_bundle = bundle or _FixedWeightBundle(0.5)
    return RebalancePipeline(
        book_state=book_state or _BookState(),
        market_data=market_data or _MarketData(),
        book=assemble_test_book(
            config,
            {config.sleeves[0].wheel_filename: loaded_bundle},
        ),
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=arrays or SleeveArrays.bar_only(),
    )


def _started_pipeline(
    *,
    book_state: _BookState | None = None,
    market_data: _MarketData | None = None,
    book: BookConfig | None = None,
    bundle: ExecutionBundle | None = None,
    arrays: SleeveArrays | None = None,
) -> RebalancePipeline:
    pipeline = _pipeline(
        book_state=book_state,
        market_data=market_data,
        book=book,
        bundle=bundle,
        arrays=arrays,
    )
    startup_result = pipeline.startup_check()
    assert startup_result.trading_enabled is True
    return pipeline


def test_rebalance_pipeline_returns_sized_orders_and_summary() -> None:
    result = _started_pipeline().rebalance(_all_due())

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
    es_bars: dict[InstrumentId, tuple[MarketBar, ...]] = {
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
        book=assemble_test_book(
            _book(),
            {"trend.whl": _ContinuousWeightBundle(0.5)},
        ),
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=SleeveArrays.bar_only(),
    )

    startup_result = pipeline.startup_check()
    result = pipeline.rebalance(_all_due())

    assert startup_result.trading_enabled is True
    assert result.orders[0].instrument_id == _ES
    assert result.orders[0].side == OrderSide.BUY


def test_rebalance_pipeline_intersects_drop_policy_mixed_calendar_panel() -> None:
    bundle = _CalendarParityBundle()
    pipeline = _started_pipeline(
        market_data=_MarketData(
            bars_by_instrument_id=_mixed_calendar_bars(),
            fresh_instrument_ids=frozenset({_LSE_LEG, _BRU_LEG}),
        ),
        bundle=bundle,
    )

    result = pipeline.rebalance(_all_due())

    expected_index = pd.DatetimeIndex([0, _DAY_NS, 4 * _DAY_NS])
    expected_close = pd.DataFrame(
        {
            _LSE_LEG: [10.0, 11.0, 40.0],
            _BRU_LEG: [12.0, 13.0, 60.0],
        },
        index=expected_index,
    )
    expected_weights = pd.DataFrame(
        {
            _LSE_LEG: [0.45454545454545453, 0.4583333333333333, 0.4],
            _BRU_LEG: [0.5454545454545454, 0.5416666666666666, 0.6],
        },
        index=expected_index,
    )
    expected_weights.columns.name = "instrument_id"

    assert result.halt_reason is None
    assert result.summary.num_sleeves == 1
    assert result.summary.num_targets == 2
    assert bundle.close_panel is not None
    assert bundle.weights is not None
    pd.testing.assert_frame_equal(bundle.close_panel, expected_close)
    assert not bundle.close_panel.isna().any().any()
    pd.testing.assert_frame_equal(bundle.weights, expected_weights)


def test_custom_arrays_use_the_union_index_for_nan_policy(tmp_path: Path) -> None:
    bundle = _CalendarParityBundle(
        missing_index=MissingIndexPolicy.NAN,
        custom_arrays=True,
    )

    pipeline = _started_pipeline(
        market_data=_MarketData(
            bars_by_instrument_id=_mixed_calendar_bars(),
            fresh_instrument_ids=frozenset({_LSE_LEG, _BRU_LEG}),
        ),
        bundle=bundle,
        arrays=SleeveArrays.live(
            catalog=Catalog.open(tmp_path),
            providers={FixtureRecord: _EmptyCustomProvider()},
        ),
    )

    pipeline.rebalance(_all_due())

    expected_index = pd.DatetimeIndex([_DAY_NS, 2 * _DAY_NS, 3 * _DAY_NS, 4 * _DAY_NS])
    assert bundle.fixture_panel is not None
    assert bundle.fixture_panel.index.equals(expected_index)


def test_rebalance_pipeline_holds_when_drop_policy_has_too_few_common_bars() -> None:
    bundle = _CalendarParityBundle()
    bars = _mixed_calendar_bars()
    bars[_BRU_LEG] = (
        MarketBar(2 * _DAY_NS, 22.0, 22.0, 22.0, 22.0, 1_000.0),
        MarketBar(3 * _DAY_NS, 30.0, 30.0, 30.0, 30.0, 1_000.0),
        MarketBar(4 * _DAY_NS, 60.0, 60.0, 60.0, 60.0, 1_000.0),
    )
    pipeline = _started_pipeline(
        market_data=_MarketData(
            bars_by_instrument_id=bars,
            fresh_instrument_ids=frozenset({_LSE_LEG, _BRU_LEG}),
        ),
        bundle=bundle,
    )

    result = pipeline.rebalance(_all_due())

    assert result.orders == ()
    assert result.summary.num_sleeves == 0
    assert result.halt_reason is None


def test_rebalance_pipeline_surfaces_raise_policy_misalignment_as_sleeve_failure() -> (
    None
):
    # The raise policy still refuses to compute on a misaligned panel, but the
    # refusal is bounded to the sleeve (aegis-rd-hd54): surfaced, never propagated.
    pipeline = _started_pipeline(
        market_data=_MarketData(
            bars_by_instrument_id=_mixed_calendar_bars(),
            fresh_instrument_ids=frozenset({_LSE_LEG, _BRU_LEG}),
        ),
        bundle=_CalendarParityBundle(missing_index=MissingIndexPolicy.RAISE),
    )

    result = pipeline.rebalance(_all_due())

    assert result.orders == ()
    assert [failure.sleeve for failure in result.sleeve_failures] == [_SLEEVE]
    assert "MissingIndexAlignmentError" in result.sleeve_failures[0].reason
    assert "missing_index='raise'" in result.sleeve_failures[0].reason


def test_rebalance_pipeline_does_not_expose_mutable_ledger() -> None:
    pipeline = _pipeline()

    exposes_mutable_ledger = hasattr(pipeline, "sleeve_ledger")

    assert exposes_mutable_ledger is False


def test_rebalance_pipeline_uses_bands_proven_by_book_assembly() -> None:
    pipeline = _pipeline(
        book_state=_BookState({_INSTRUMENT_ID: 0.45}),
        bundle=_FixedWeightBundle(0.5, band=DriftBand.symmetric(0.10)),
    )

    startup_result = pipeline.startup_check()
    result = pipeline.rebalance(_all_due())

    assert startup_result.trading_enabled is True
    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.PASS


def test_apply_roll_rebases_ledger_by_spread_event() -> None:
    ledger = SleeveLedger(horizon=derive_horizon(("1D",)))
    _record_close(ledger, 100.0, 0)
    _record_close(ledger, 110.0, 1)
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=assemble_test_book(
            _book(),
            {"trend.whl": _ContinuousWeightBundle(0.5)},
        ),
        ledger=ledger,
        arrays=SleeveArrays.bar_only(),
    )

    pipeline.apply_roll(RollEvent(continuous_id=_ES, rebasing=spread_rebasing(50.0)))
    _record_close(ledger, 170.0, 2)
    attribution = ledger.attribution({_SLEEVE: 1.0})

    assert attribution[_SLEEVE] == pytest.approx(12.9166666667)


def test_apply_roll_rebases_ledger_by_ratio_event() -> None:
    ledger = SleeveLedger(horizon=derive_horizon(("1D",)))
    _record_close(ledger, 100.0, 0)
    _record_close(ledger, 110.0, 1)
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=assemble_test_book(
            _book(),
            {"trend.whl": _ContinuousWeightBundle(0.5)},
        ),
        ledger=ledger,
        arrays=SleeveArrays.bar_only(),
    )

    pipeline.apply_roll(RollEvent(continuous_id=_ES, rebasing=ratio_rebasing(1.5)))
    _record_close(ledger, 180.0, 2)
    attribution = ledger.attribution({_SLEEVE: 1.0})

    assert attribution[_SLEEVE] == pytest.approx(19.0909090909)


def test_rebalance_pipeline_filters_orders_when_market_data_reports_stale_instrument() -> (
    None
):
    result = _started_pipeline(
        market_data=_MarketData(fresh_instrument_ids=frozenset())
    ).rebalance(_all_due())

    assert result.orders == ()
    assert result.summary.num_targets == 1
    assert result.summary.num_orders == 0


def test_rebalance_pipeline_does_not_gate_held_book_when_every_sleeve_fails() -> None:
    result = _started_pipeline(
        book=_book(gross_cap=0.60),
        book_state=_BookState({_INSTRUMENT_ID: 0.70}),
        bundle=_PoisonFixedInstrumentBundle(0.50),
    ).rebalance(_all_due())

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.PASS
    assert result.halt_reason is None
    assert [failure.sleeve for failure in result.sleeve_failures] == [_SLEEVE]


def test_rebalance_pipeline_reports_gate_error_in_summary() -> None:
    result = _started_pipeline(
        book=_book(per_name_cap=0.5),
        book_state=_BookState({_INSTRUMENT_ID: 0.7}),
        bundle=_FixedWeightBundle(0.8),
    ).rebalance(_all_due())

    assert result.orders == ()
    assert result.summary.gate_outcome == GateOutcome.ERROR
    assert result.halt_reason is not None
    assert "InstrumentId PIPE.XNYS" in result.halt_reason
    assert "unfixable" in result.halt_reason


def test_startup_check_passes_when_band_and_integrity_gates_pass() -> None:
    result = _pipeline().startup_check()

    assert result.trading_enabled is True
    assert result.should_halt is False
    assert result.halt_gate is None
    assert result.halt_reason is None
    assert result.nav == 100_000.0
    assert result.cash == 100_000.0


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


def _two_sleeve_pipeline(
    healthy_bundle: ExecutionBundle, poison_bundle: ExecutionBundle
) -> RebalancePipeline:
    bars = _bars_by_instrument_id()
    bars[_LSE_LEG] = (
        MarketBar(0, 10.0, 10.0, 10.0, 10.0, 1_000.0),
        MarketBar(_DAY_NS, 11.0, 11.0, 11.0, 11.0, 1_000.0),
    )
    book = BookConfig(
        sleeves=(
            SleeveConfig(name=_SLEEVE, wheel_filename="trend.whl", risk_share=0.5),
            SleeveConfig(
                name=SleeveName("poison"), wheel_filename="poison.whl", risk_share=0.5
            ),
        ),
        base_currency="EUR",
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(
            bars_by_instrument_id=bars,
            fresh_instrument_ids=frozenset({_INSTRUMENT_ID, _LSE_LEG}),
        ),
        book=assemble_test_book(
            book,
            {
                "trend.whl": healthy_bundle,
                "poison.whl": poison_bundle,
            },
        ),
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=SleeveArrays.bar_only(),
    )
    startup_result = pipeline.startup_check()
    assert startup_result.trading_enabled is True
    return pipeline


def test_rebalance_pipeline_isolates_a_sleeve_whose_compute_raises() -> None:
    # aegis-rd-hd54: one sleeve's compute failure must not abort the book —
    # the healthy sleeve still rebalances and the failure is surfaced, not raised.
    pipeline = _two_sleeve_pipeline(_FixedWeightBundle(0.5), _PoisonBundle())

    result = pipeline.rebalance(_all_due(_SLEEVE, SleeveName("poison")))

    assert result.summary.gate_outcome == GateOutcome.PASS
    assert [failure.sleeve for failure in result.sleeve_failures] == [
        SleeveName("poison")
    ]
    assert "component exploded" in result.sleeve_failures[0].reason
    assert result.summary.num_sleeves == 1
    assert [order.instrument_id for order in result.orders] == [_INSTRUMENT_ID]
    assert result.orders[0].side == OrderSide.BUY
    assert result.orders[0].quantity > 0.0


def test_rebalance_pipeline_failing_sleeve_holds_without_orders() -> None:
    # The failing sleeve's disposition is HOLD: no orders for its instruments,
    # no fabricated weights.
    pipeline = _two_sleeve_pipeline(_FixedWeightBundle(0.5), _PoisonBundle())

    result = pipeline.rebalance(_all_due(_SLEEVE, SleeveName("poison")))

    assert _LSE_LEG not in {order.instrument_id for order in result.orders}


def test_rebalance_pipeline_surfaces_failures_when_every_sleeve_fails() -> None:
    # All sleeves failing must still return a result (no orders), never raise.
    pipeline = _two_sleeve_pipeline(_PoisonFixedInstrumentBundle(0.5), _PoisonBundle())

    result = pipeline.rebalance(_all_due(_SLEEVE, SleeveName("poison")))

    assert result.orders == ()
    assert {failure.sleeve for failure in result.sleeve_failures} == {
        SleeveName("poison"),
        SleeveName("trend"),
    }


# ---------------------------------------------------------------------------
# FX conversion legs (aegis-rd-reyj): compute on base-currency panels
# ---------------------------------------------------------------------------

_EURUSD = InstrumentId.from_str("EUR/USD.IDEALPRO")


class _SpyConversionBundle(ExecutionBundle):
    """Fixed-weight bundle over a USD-quoted instrument that records the native
    Close panel and the conversion its compute received, so a test can pin the
    native-price boundary: the trader hands over native arrays plus the resolved
    conversion and never pre-converts."""

    def __init__(self, weight: float) -> None:
        self._weight = weight
        self.seen_close: pd.DataFrame | None = None
        self.seen_conversion: CurrencyConversion | None = None
        contract = DataContract(
            instrument_ids=(_INSTRUMENT_ID,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            exchange=(_EURUSD,),
        )
        manifest = BundleManifest(
            run_id="pipeline-fx-test",
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
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        self.seen_close = close
        self.seen_conversion = currency_conversion
        target = pd.DataFrame(
            {_INSTRUMENT_ID: [self._weight] * len(close)},
            index=close.index,
        )
        target.columns.name = "instrument_id"
        return target


def _fx_market_data() -> _MarketData:
    return _MarketData(
        bars_by_instrument_id={
            _INSTRUMENT_ID: (
                MarketBar(0, 100.0, 100.0, 100.0, 100.0, 1_000.0),
                MarketBar(_DAY_NS, 100.0, 100.0, 100.0, 100.0, 1_000.0),
            ),
            # EUR/USD at 1.25: a USD close of 100 is 80 EUR.
            _EURUSD: (
                MarketBar(0, 1.25, 1.25, 1.25, 1.25, 0.0),
                MarketBar(_DAY_NS, 1.25, 1.25, 1.25, 1.25, 0.0),
            ),
        },
        currencies={_INSTRUMENT_ID: "USD"},
        pairs={_EURUSD: ("EUR", "USD")},
        fx_rates={"USD": 1.25},
    )


def test_sleeve_compute_receives_native_prices_and_the_resolved_conversion() -> None:
    """The native-price boundary (aegis-rd-tkj5.4): the pipeline resolves the
    period's conversion but hands the bundle NATIVE arrays plus that conversion —
    the bundle owns applying it, so it is applied exactly once. The resolved
    conversion still produces research's EUR view (aegis-rd-reyj)."""
    bundle = _SpyConversionBundle(0.5)
    pipeline = _started_pipeline(market_data=_fx_market_data(), bundle=bundle)

    result = pipeline.rebalance(_all_due())

    assert result.sleeve_failures == ()
    assert bundle.seen_close is not None
    # Native USD closes, not a pre-converted panel.
    assert bundle.seen_close[_INSTRUMENT_ID].tolist() == pytest.approx([100.0, 100.0])
    # The resolved conversion is the one typed transformation: applying it yields
    # the EUR view research validated on (USD 100 at EUR/USD 1.25 -> EUR 80).
    assert bundle.seen_conversion is not None
    converted = bundle.seen_conversion.apply(
        MarketDataBundle({"Close": bundle.seen_close})
    ).array("Close")
    assert converted[_INSTRUMENT_ID].tolist() == pytest.approx([80.0, 80.0])
    assert [order.instrument_id for order in result.orders] == [_INSTRUMENT_ID]


class _SpyContinuousConversionBundle(ExecutionBundle):
    """Records the native panel + conversion for a USD-quoted continuous root in a
    EUR-base book — the research/trader continuous-root parity double."""

    def __init__(self) -> None:
        self.seen_close: pd.DataFrame | None = None
        self.seen_conversion: CurrencyConversion | None = None
        contract = DataContract(
            instrument_ids=(_ES,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            futures=("ES",),
            adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
            exchange=(_EURUSD,),
        )
        manifest = BundleManifest(
            run_id="pipeline-continuous-fx-test",
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
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        self.seen_close = close
        self.seen_conversion = currency_conversion
        target = pd.DataFrame({_ES: [0.5] * len(close)}, index=close.index)
        target.columns.name = "instrument_id"
        return target


def test_continuous_root_conversion_matches_the_research_view_under_moving_fx() -> None:
    """Research/Trader continuous-root currency parity (aegis-rd-tkj5.4): from the
    same native ES closes and the same moving EUR/USD series, the trader's resolved
    conversion produces the identical base-currency panel research's catalog adapter
    pins (5000/1.25, 5010/1.20). Trader derives the root's USD from its front leg;
    research derives it from all dated legs — same code, same builder, same view."""
    market_data = _MarketData(
        bars_by_instrument_id={
            _ES: (
                MarketBar(0, 5000.0, 5000.0, 5000.0, 5000.0, 1_000.0),
                MarketBar(_DAY_NS, 5010.0, 5010.0, 5010.0, 5010.0, 1_000.0),
            ),
            _EURUSD: (
                MarketBar(0, 1.25, 1.25, 1.25, 1.25, 0.0),
                MarketBar(_DAY_NS, 1.20, 1.20, 1.20, 1.20, 0.0),
            ),
        },
        fresh_instrument_ids=frozenset({_ES}),
        currencies={_ES: "USD"},
        pairs={_EURUSD: ("EUR", "USD")},
        fx_rates={"USD": 1.25},
    )
    bundle = _SpyContinuousConversionBundle()
    pipeline = _started_pipeline(market_data=market_data, bundle=bundle)

    result = pipeline.rebalance(_all_due())

    assert result.sleeve_failures == ()
    assert bundle.seen_close is not None
    assert bundle.seen_close[_ES].tolist() == pytest.approx([5000.0, 5010.0])
    assert bundle.seen_conversion is not None
    converted = bundle.seen_conversion.apply(
        MarketDataBundle({"Close": bundle.seen_close})
    ).array("Close")
    # The exact base-currency panel research's catalog adapter derives for the same
    # native prices and FX series (see test_catalog_adapter_converts_a_non_base_
    # continuous_root_through_exchange_fx in aegis-rd).
    assert converted[_ES].tolist() == pytest.approx([5000.0 / 1.25, 5010.0 / 1.20])


def test_missing_fx_bars_fail_the_sleeve_closed_not_the_book() -> None:
    """A conversion leg with no bars must surface as a sleeve failure (hold),
    never a silent native-priced compute."""
    market_data = _MarketData(
        bars_by_instrument_id={
            _INSTRUMENT_ID: (
                MarketBar(0, 100.0, 100.0, 100.0, 100.0, 1_000.0),
                MarketBar(_DAY_NS, 100.0, 100.0, 100.0, 100.0, 1_000.0),
            ),
        },
        currencies={_INSTRUMENT_ID: "USD"},
        pairs={_EURUSD: ("EUR", "USD")},
    )
    bundle = _SpyConversionBundle(0.5)
    pipeline = _started_pipeline(market_data=market_data, bundle=bundle)

    result = pipeline.rebalance(_all_due())

    assert bundle.seen_close is None
    assert [failure.sleeve for failure in result.sleeve_failures] == [_SLEEVE]
    assert result.orders == ()


# ---------------------------------------------------------------------------
# Independently due Sleeves carry their own period coordinates (aegis-rd-9qkr.2)
# ---------------------------------------------------------------------------


class _PeriodRecordingMarketData(_MarketData):
    """Records the period coordinates of every lookback read, per instrument."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.read_periods: dict[InstrumentId, int] = {}

    def lookback_window(
        self,
        instrument_id: InstrumentId,
        _timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ):
        self.read_periods[instrument_id] = period
        return super().lookback_window(
            instrument_id, _timeframe, period=period, period_ns=period_ns, limit=limit
        )


def test_each_due_sleeve_computes_on_its_own_period_coordinates() -> None:
    bars = _bars_by_instrument_id()
    bars[_LSE_LEG] = (
        MarketBar(0, 10.0, 10.0, 10.0, 10.0, 1_000.0),
        MarketBar(_DAY_NS, 11.0, 11.0, 11.0, 11.0, 1_000.0),
    )
    slow = SleeveName("slow")
    book = BookConfig(
        sleeves=(
            SleeveConfig(name=_SLEEVE, wheel_filename="trend.whl", risk_share=0.5),
            SleeveConfig(name=slow, wheel_filename="slow.whl", risk_share=0.5),
        ),
        base_currency="EUR",
    )
    market_data = _PeriodRecordingMarketData(
        bars_by_instrument_id=bars,
        fresh_instrument_ids=frozenset({_INSTRUMENT_ID, _LSE_LEG}),
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=market_data,
        book=assemble_test_book(
            book,
            {
                "trend.whl": _FixedWeightBundle(0.5),
                "slow.whl": _PoisonBundle(),
            },
        ),
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=SleeveArrays.bar_only(),
    )

    pipeline.rebalance(
        RebalanceRequest(
            due=(
                DueSleeve(
                    sleeve=_SLEEVE,
                    period=CompletedRebalancePeriod(period=24, period_ns=_DAY_NS),
                ),
                DueSleeve(
                    sleeve=slow,
                    period=CompletedRebalancePeriod(period=1, period_ns=_DAY_NS),
                ),
            ),
            timestamp_ns=25 * _DAY_NS,
        )
    )

    assert market_data.read_periods[_INSTRUMENT_ID] == 24
    assert market_data.read_periods[_LSE_LEG] == 1


def test_market_observation_records_the_full_book_without_invoking_sleeves() -> None:
    # aegis-rd-9qkr.7: a relevant stream advance records a timestamped
    # full-Book observation even when no Sleeve is due.  The poison bundle
    # proves no Execution Bundle is invoked on this path.
    ledger = SleeveLedger(horizon=derive_horizon(("1D",)))
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=assemble_test_book(_book(), {"trend.whl": _PoisonBundle()}),
        ledger=ledger,
        arrays=SleeveArrays.bar_only(),
    )

    pipeline.record_market_observation(_DAY_NS, {_LSE_LEG: 11.0})
    pipeline.record_market_observation(2 * _DAY_NS, {_LSE_LEG: 12.0})

    assert ledger.observation_count == 2
    assert ledger.nav_history == (100_000.0, 100_000.0)


class _StreamRecordingMarketData(_MarketData):
    """Records every (instrument, timeframe) lookback read — stream identity."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.read_streams: set[tuple[InstrumentId, str]] = set()

    def lookback_window(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ):
        self.read_streams.add((instrument_id, timeframe))
        return super().lookback_window(
            instrument_id, timeframe, period=period, period_ns=period_ns, limit=limit
        )


class _ConversionSleeveBundle(ExecutionBundle):
    """A fixed-weight sleeve over one USD instrument with an FX conversion leg,
    at a caller-chosen timeframe."""

    def __init__(self, instrument_id: InstrumentId, timeframe: str) -> None:
        self._instrument_id = instrument_id
        contract = DataContract(
            instrument_ids=(instrument_id,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe=timeframe,
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            exchange=(_EURUSD,),
        )
        manifest = BundleManifest(
            run_id="pipeline-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            instrument_ids=(instrument_id,),
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
            instrument_bands={instrument_id: DriftBand.symmetric(0.0)},
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        target = pd.DataFrame(
            {self._instrument_id: [0.5] * len(close)}, index=close.index
        )
        target.columns.name = "instrument_id"
        return target


def test_shared_fx_leg_serves_each_sleeve_at_its_own_timeframe() -> None:
    # One reference InstrumentId consumed at two timeframes (aegis-rd-9qkr.4):
    # each sleeve's conversion window reads the concrete (id, timeframe) stream,
    # never a collapsed per-instrument timeframe.
    hourly = SleeveName("hourly")
    fx_bars = (
        MarketBar(0, 1.25, 1.25, 1.25, 1.25, 0.0),
        MarketBar(_DAY_NS, 1.25, 1.25, 1.25, 1.25, 0.0),
    )
    market_data = _StreamRecordingMarketData(
        bars_by_instrument_id={
            _INSTRUMENT_ID: (
                MarketBar(0, 100.0, 100.0, 100.0, 100.0, 1_000.0),
                MarketBar(_DAY_NS, 100.0, 100.0, 100.0, 100.0, 1_000.0),
            ),
            _LSE_LEG: (
                MarketBar(0, 10.0, 10.0, 10.0, 10.0, 1_000.0),
                MarketBar(_DAY_NS, 11.0, 11.0, 11.0, 11.0, 1_000.0),
            ),
            _EURUSD: fx_bars,
        },
        fresh_instrument_ids=frozenset({_INSTRUMENT_ID, _LSE_LEG}),
        currencies={_INSTRUMENT_ID: "USD", _LSE_LEG: "USD"},
        pairs={_EURUSD: ("EUR", "USD")},
        fx_rates={"USD": 1.25},
    )
    book = BookConfig(
        sleeves=(
            SleeveConfig(name=_SLEEVE, wheel_filename="trend.whl", risk_share=0.5),
            SleeveConfig(name=hourly, wheel_filename="hourly.whl", risk_share=0.5),
        ),
        base_currency="EUR",
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=market_data,
        book=assemble_test_book(
            book,
            {
                "trend.whl": _ConversionSleeveBundle(_INSTRUMENT_ID, "1D"),
                "hourly.whl": _ConversionSleeveBundle(_LSE_LEG, "1H"),
            },
        ),
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=SleeveArrays.bar_only(),
    )

    result = pipeline.rebalance(_all_due(_SLEEVE, hourly))

    assert result.sleeve_failures == ()
    assert (_EURUSD, "1D") in market_data.read_streams
    assert (_EURUSD, "1H") in market_data.read_streams
