from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from aegis_runtime import ExecutionBundle
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.catalog import CatalogBackedDataPort
from aegis_data.marking import DeclaredMarkingResolver, MarkMode
from aegis_data.testing import FakeCatalog, es_port_two_rolls
from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.analytics_horizon import derive_horizon
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.roll import Halt, SubscribeBars
from aegis_trader.domain.startup import StartupGate
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    DueSleeve,
    RebalancePipeline,
    RebalanceRequest,
    RebalanceResult,
)
from aegis_trader.trader.book_market_clock import BookMarketClock
from aegis_trader.trader.sleeve_arrays import SleeveArrays
from aegis_trader.trader.roll_desk import RollDesk
from aegis_trader.bundles.marking import RecordedMarkingResolver
from aegis_trader.trader.startup_fast_forward import (
    Ready,
    Recovering,
    RecoveryUpdate,
    StartupFastForward,
)
from tests.support.factories import assemble_test_book, make_bundle

_INSTRUMENT = InstrumentId.from_str("SPY.ARCA")
_WEEKLY_INSTRUMENT = InstrumentId.from_str("QQQ.NASDAQ")
_SLEEVE = SleeveName("trend")
_WEEKLY_SLEEVE = SleeveName("carry")
_DAY_NS = 86_400_000_000_000
_WEEK_NS = 604_800_000_000_000
_FIRST_NS = 1_752_710_400_000_000_000
_SECOND_NS = _FIRST_NS + _DAY_NS
_THIRD_NS = _SECOND_NS + _DAY_NS
_SECOND_WITHIN_PERIOD_NS = 1_752_796_800_000_000_001
_SECOND_MINUS_WEEK_NS = 1_752_192_000_000_000_000
_SECOND_PLUS_WEEK_NS = 1_753_401_600_000_000_000
_THROUGH = datetime(2025, 7, 19, tzinfo=timezone.utc)
_ES = InstrumentId.from_str("ES.XCME")
_ESM4 = InstrumentId.from_str("ESM4.XCME")
_ESU4 = InstrumentId.from_str("ESU4.XCME")


class _BookState:
    def nav(self) -> float:
        return 100_000.0

    def cash(self) -> float:
        return 100_000.0

    def is_cache_healthy(self) -> bool:
        return True

    def realized_weights(self) -> dict[InstrumentId, float]:
        return {}


class _MarketData:
    def __init__(self, bars: tuple[MarketBar, ...] | None = None) -> None:
        self._bars = bars or (
            _market_bar(_FIRST_NS, 100.0),
            _market_bar(_SECOND_NS, 101.0),
        )

    def instrument_sizing(self, instrument_id: InstrumentId) -> InstrumentSizing:
        return InstrumentSizing(currency="EUR", size_increment=1.0)

    def make_quantity(self, instrument_id: InstrumentId, raw_shares: float) -> float:
        return raw_shares

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        return instrument_id

    def currency_pair(self, instrument_id: InstrumentId) -> tuple[str, str] | None:
        return None

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        return 1.0

    def lookback_window(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        right_edge = (period + 1) * period_ns
        return tuple(bar for bar in self._bars if bar.ts_event < right_edge)[-limit:]

    def has_bar_in_period(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        return True


class _FixedBundle(ExecutionBundle):
    def __init__(self, bundle: ExecutionBundle) -> None:
        super().__init__(
            contract=bundle.contract,
            manifest=bundle.manifest,
            plan=bundle._plan,  # noqa: SLF001 - clone the test fixture bundle
        )

    def compute_weights(
        self,
        native_prices: Any,
        *,
        currency_conversion: Any = None,
    ) -> pd.DataFrame:
        index = native_prices.array("Close").index
        target = pd.DataFrame(
            {
                instrument_id: [0.5] * len(index)
                for instrument_id in self.contract.instrument_ids
            },
            index=index,
        )
        target.columns.name = "instrument_id"
        return target


class _FailingBundle(_FixedBundle):
    def compute_weights(
        self,
        native_prices: Any,
        *,
        currency_conversion: Any = None,
    ) -> pd.DataFrame:
        raise RuntimeError("fixture compute failed")


class _CloseWeightBundle(_FixedBundle):
    def compute_weights(
        self,
        native_prices: Any,
        *,
        currency_conversion: Any = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        target = pd.DataFrame({_INSTRUMENT: close.iloc[:, 0] / 100.0})
        target.columns.name = "instrument_id"
        return target


def test_fast_forward_releases_subscriptions_after_the_book_history_barrier() -> None:
    fast_forward, pipeline = _fast_forward()
    through = _THROUGH

    loading = fast_forward.begin(through=through)
    assert isinstance(loading, Recovering)
    request = loading.requests[0]
    still_loading = fast_forward.receive_history(
        _bar(request.bar_type, _SECOND_NS, 101.0)
    )
    fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 100.0))
    ready = fast_forward.history_loaded(request.key)

    assert loading.progress.loaded_requests == 0
    assert isinstance(still_loading, Recovering)
    assert still_loading.requests == ()
    assert isinstance(ready, Ready)
    assert ready.intents == (SubscribeBars(_INSTRUMENT, "1D"),)
    assert ready.book_activity == _SECOND_NS
    assert pipeline.observation_count == 3


def test_fast_forward_leaves_the_live_clock_at_the_replayed_book_frontier() -> None:
    fast_forward, _pipeline, market_clock = _fast_forward_with_clock()
    loading = _require_recovering(fast_forward.begin(through=_THROUGH))
    request = loading.requests[0]
    fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 100.0))
    fast_forward.receive_history(_bar(request.bar_type, _SECOND_NS, 101.0))
    ready = fast_forward.history_loaded(request.key)

    market_clock.advance(request.bar_type, _SECOND_WITHIN_PERIOD_NS)
    within_period_due = market_clock.drain()
    market_clock.advance(request.bar_type, _THIRD_NS)
    next_period_due = market_clock.drain()

    assert isinstance(ready, Ready)
    assert within_period_due == ()
    assert next_period_due == (
        DueSleeve(
            sleeve=_SLEEVE,
            period=CompletedRebalancePeriod(
                period=20_287,
                period_ns=_DAY_NS,
            ),
        ),
    )


def test_fast_forward_halts_a_conflicting_live_boundary_bar() -> None:
    fast_forward, _pipeline = _fast_forward()
    loading = fast_forward.begin(through=_THROUGH)
    assert isinstance(loading, Recovering)
    request = loading.requests[0]
    fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 100.0))
    fast_forward.receive_history(_bar(request.bar_type, _SECOND_NS, 101.0))
    ready = fast_forward.history_loaded(request.key)
    assert isinstance(ready, Ready)

    outcome = ready.admit_live(_bar(request.bar_type, _SECOND_NS, 999.0))

    assert isinstance(outcome, Halt)
    assert outcome.gate == StartupGate.RECOVERY_HISTORY


def test_fast_forward_ignores_an_identical_live_boundary_bar() -> None:
    fast_forward, _pipeline = _fast_forward()
    loading = fast_forward.begin(through=_THROUGH)
    assert isinstance(loading, Recovering)
    request = loading.requests[0]
    boundary = _bar(request.bar_type, _SECOND_NS, 101.0)
    fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 100.0))
    fast_forward.receive_history(boundary)
    ready = fast_forward.history_loaded(request.key)
    assert isinstance(ready, Ready)

    outcome = ready.admit_live(boundary)

    assert outcome is False


def test_fast_forward_halts_a_conflicting_historical_duplicate() -> None:
    fast_forward, _pipeline = _fast_forward()
    loading = fast_forward.begin(through=_THROUGH)
    assert isinstance(loading, Recovering)
    request = loading.requests[0]
    fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 100.0))

    outcome = fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 999.0))

    assert isinstance(outcome, Halt)
    assert outcome.gate == StartupGate.RECOVERY_HISTORY


def test_fast_forward_halts_an_incomplete_required_history_window() -> None:
    fast_forward, _pipeline = _fast_forward()
    loading = fast_forward.begin(through=_THROUGH)
    assert isinstance(loading, Recovering)
    request = loading.requests[0]
    fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 100.0))

    outcome = fast_forward.history_loaded(request.key)

    assert isinstance(outcome, Halt)
    assert outcome.gate == StartupGate.RECOVERY_HISTORY


def test_fast_forward_is_independent_of_callback_order_and_identical_duplicates() -> (
    None
):
    ordered_ready, ordered_result, ordered_weights = _recover_two_streams(
        reverse_delivery=False
    )
    reversed_ready, reversed_result, reversed_weights = _recover_two_streams(
        reverse_delivery=True
    )

    assert reversed_ready == ordered_ready
    assert reversed_result.orders == ordered_result.orders
    assert reversed_weights == ordered_weights


def test_fast_forward_keeps_its_terminal_outcome_for_late_deliveries() -> None:
    fast_forward, _pipeline = _fast_forward()
    loading = fast_forward.begin(through=_THROUGH)
    assert isinstance(loading, Recovering)
    request = loading.requests[0]
    fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 100.0))
    fast_forward.receive_history(_bar(request.bar_type, _SECOND_NS, 101.0))
    ready = fast_forward.history_loaded(request.key)

    late_data = fast_forward.receive_history(
        _bar(request.bar_type, _SECOND_NS + _DAY_NS, 102.0)
    )
    late_callback = fast_forward.history_loaded(request.key)

    assert isinstance(ready, Ready)
    assert late_data is ready
    assert late_callback is ready


def test_fast_forward_reconstructs_rolls_before_releasing_the_live_front() -> None:
    port, native = es_port_two_rolls()
    present = {_ESU4}
    roll_desk = RollDesk(
        catalog_port=port,
        instrument_present=present.__contains__,
    )
    book_config = BookConfig(
        sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
        base_currency="EUR",
    )
    book = assemble_test_book(
        book_config,
        {
            "trend.whl": _FixedBundle(
                make_bundle(
                    native_instrument_ids=(),
                    continuous_futures={"ES": _ES},
                    adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
                    lookback_bars=80,
                )
            )
        },
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=book,
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=SleeveArrays.bar_only(),
    )
    resolver = DeclaredMarkingResolver()
    fast_forward = StartupFastForward(
        book=book,
        pipeline=pipeline,
        roll_desk=roll_desk,
        bar_type_resolver=resolver,
        book_market_clock=BookMarketClock(
            book=book,
            bar_type_resolver=resolver,
        ),
        fx_reference_pairs=(),
    )
    loading = fast_forward.begin(through=datetime(2024, 7, 1, tzinfo=timezone.utc))
    assert isinstance(loading, Recovering)

    outcome = _complete_futures_history(fast_forward, loading, native)

    assert isinstance(outcome, Ready)
    assert {request.bar_type.instrument_id for request in loading.requests} == set(
        native
    )
    assert outcome.intents == (SubscribeBars(_ESU4, "1D"),)
    assert roll_desk.front_leg(_ES) == _ESU4


def test_fast_forward_continuous_state_matches_uninterrupted_processing() -> None:
    port, native = es_port_two_rolls()
    fast_forward, recovered_desk, book = _futures_fast_forward(port)
    loading = fast_forward.begin(through=datetime(2024, 7, 1, tzinfo=timezone.utc))
    assert isinstance(loading, Recovering)

    outcome = _complete_futures_history(fast_forward, loading, native)
    uninterrupted_desk = _process_uninterrupted_futures(port, book, loading, native)
    recovered_series = recovered_desk.series(_ES)
    uninterrupted_series = uninterrupted_desk.series(_ES)

    assert isinstance(outcome, Ready)
    assert recovered_series is not None
    assert uninterrupted_series is not None
    pd.testing.assert_frame_equal(recovered_series, uninterrupted_series)
    assert recovered_desk.front_leg(_ES) == uninterrupted_desk.front_leg(_ES)


def test_fast_forward_halts_when_the_current_futures_leg_has_no_history() -> None:
    outcome = _recover_futures_without(_ESU4)

    assert isinstance(outcome, Halt)
    assert outcome.gate == StartupGate.RECOVERY_HISTORY


def test_fast_forward_halts_when_a_futures_roll_transition_is_unavailable() -> None:
    outcome = _recover_futures_without(_ESM4)

    assert isinstance(outcome, Halt)
    assert outcome.gate == StartupGate.RECOVERY_HISTORY


def test_fast_forward_does_not_invent_a_calendar_freshness_deadline() -> None:
    port, native = es_port_two_rolls()
    fast_forward, _roll_desk, _book = _futures_fast_forward(port)
    loading = fast_forward.begin(through=datetime(2024, 7, 8, tzinfo=timezone.utc))
    assert isinstance(loading, Recovering)
    closure_history = _history_through(
        native,
        datetime(2024, 7, 3, tzinfo=timezone.utc),
    )

    outcome = _complete_futures_history(fast_forward, loading, closure_history)

    assert isinstance(outcome, Ready)


def test_fast_forward_halts_when_quote_marking_sides_do_not_share_timestamps() -> None:
    book_config = BookConfig(
        sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
        base_currency="EUR",
    )
    book = assemble_test_book(
        book_config,
        {
            "trend.whl": _FixedBundle(
                make_bundle(native_instrument_ids=(_INSTRUMENT,), lookback_bars=1)
            )
        },
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=book,
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=SleeveArrays.bar_only(),
    )
    resolver = RecordedMarkingResolver(recorded={_INSTRUMENT: MarkMode.QUOTE})
    fast_forward = StartupFastForward(
        book=book,
        pipeline=pipeline,
        roll_desk=None,
        bar_type_resolver=resolver,
        book_market_clock=BookMarketClock(
            book=book,
            bar_type_resolver=resolver,
        ),
        fx_reference_pairs=(),
    )
    loading = fast_forward.begin(through=_THROUGH)
    assert isinstance(loading, Recovering)
    bid, ask = loading.requests
    required = book.required_streams[0].history_bars
    first = _SECOND_NS - required * _DAY_NS
    for offset in range(required):
        fast_forward.receive_history(
            _bar(bid.bar_type, first + offset * _DAY_NS, 100.0)
        )
        fast_forward.receive_history(
            _bar(ask.bar_type, first + (offset + 1) * _DAY_NS, 102.0)
        )
    fast_forward.history_loaded(bid.key)

    outcome = fast_forward.history_loaded(ask.key)

    assert outcome == Halt(
        StartupGate.RECOVERY_HISTORY,
        "incomplete same-timestamp marking inputs for SPY.ARCA",
    )


def test_fast_forward_has_one_barrier_with_per_sleeve_cadence_positions() -> None:
    book_config = BookConfig(
        sleeves=(
            SleeveConfig(_SLEEVE, "trend.whl", 0.5),
            SleeveConfig(_WEEKLY_SLEEVE, "carry.whl", 0.5),
        ),
        base_currency="EUR",
    )
    book = assemble_test_book(
        book_config,
        {
            "trend.whl": _FixedBundle(
                make_bundle(native_instrument_ids=(_INSTRUMENT,), lookback_bars=1)
            ),
            "carry.whl": _FixedBundle(
                make_bundle(
                    native_instrument_ids=(_WEEKLY_INSTRUMENT,),
                    timeframe="1W",
                    lookback_bars=1,
                )
            ),
        },
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=book,
        ledger=SleeveLedger(horizon=derive_horizon(("1D", "1W"))),
        arrays=SleeveArrays.bar_only(),
    )
    resolver = DeclaredMarkingResolver()
    market_clock = BookMarketClock(
        book=book,
        bar_type_resolver=resolver,
    )
    fast_forward = StartupFastForward(
        book=book,
        pipeline=pipeline,
        roll_desk=None,
        bar_type_resolver=resolver,
        book_market_clock=market_clock,
        fx_reference_pairs=(),
    )
    loading = _require_recovering(fast_forward.begin(through=_THROUGH))
    daily = next(
        request
        for request in loading.requests
        if request.bar_type.instrument_id.symbol == _INSTRUMENT.symbol
    )
    weekly = next(
        request
        for request in loading.requests
        if request.bar_type.instrument_id.symbol == _WEEKLY_INSTRUMENT.symbol
    )
    fast_forward.receive_history(_bar(daily.bar_type, _FIRST_NS, 100.0))
    fast_forward.receive_history(_bar(daily.bar_type, _SECOND_NS, 101.0))
    fast_forward.receive_history(_bar(weekly.bar_type, _SECOND_MINUS_WEEK_NS, 200.0))
    fast_forward.receive_history(_bar(weekly.bar_type, _SECOND_NS, 201.0))

    one_loaded = fast_forward.history_loaded(daily.key)
    ready = fast_forward.history_loaded(weekly.key)
    market_clock.advance(daily.bar_type, _THIRD_NS)
    daily_due = market_clock.drain()
    market_clock.advance(weekly.bar_type, _SECOND_PLUS_WEEK_NS)
    weekly_due = market_clock.drain()

    assert isinstance(one_loaded, Recovering)
    assert isinstance(ready, Ready)
    assert daily_due == (
        DueSleeve(
            sleeve=_SLEEVE,
            period=CompletedRebalancePeriod(period=20_287, period_ns=_DAY_NS),
        ),
    )
    assert weekly_due == (
        DueSleeve(
            sleeve=_WEEKLY_SLEEVE,
            period=CompletedRebalancePeriod(
                period=2_898,
                period_ns=_WEEK_NS,
            ),
        ),
    )


def test_fast_forward_halts_when_a_sleeve_cannot_reconstruct_its_target() -> None:
    book_config = BookConfig(
        sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
        base_currency="EUR",
    )
    book = assemble_test_book(
        book_config,
        {
            "trend.whl": _FailingBundle(
                make_bundle(
                    native_instrument_ids=(_INSTRUMENT,),
                    lookback_bars=1,
                )
            )
        },
    )
    resolver = DeclaredMarkingResolver()
    fast_forward = StartupFastForward(
        book=book,
        pipeline=RebalancePipeline(
            book_state=_BookState(),
            market_data=_MarketData(),
            book=book,
            ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
            arrays=SleeveArrays.bar_only(),
        ),
        roll_desk=None,
        bar_type_resolver=resolver,
        book_market_clock=BookMarketClock(
            book=book,
            bar_type_resolver=resolver,
        ),
        fx_reference_pairs=(),
    )
    loading = fast_forward.begin(through=_THROUGH)
    assert isinstance(loading, Recovering)
    request = loading.requests[0]
    fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 100.0))
    fast_forward.receive_history(_bar(request.bar_type, _SECOND_NS, 101.0))
    fast_forward.receive_history(_bar(request.bar_type, _THIRD_NS, 102.0))

    outcome = fast_forward.history_loaded(request.key)

    assert isinstance(outcome, Halt)
    assert outcome.gate == StartupGate.RECOVERY_HISTORY


def test_fast_forward_converges_with_uninterrupted_market_processing() -> None:
    book_config = BookConfig(
        sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
        base_currency="EUR",
    )
    book = assemble_test_book(
        book_config,
        {
            "trend.whl": _CloseWeightBundle(
                make_bundle(native_instrument_ids=(_INSTRUMENT,), lookback_bars=30)
            )
        },
    )
    through_ns = int(_THROUGH.timestamp() * 1_000_000_000)
    history = tuple(
        _market_bar(through_ns - (34 - day) * _DAY_NS, 10.0 + day / 10.0)
        for day in range(35)
    )
    live_bar = _market_bar(through_ns + _DAY_NS, 12.5)
    market_bars = (*history, live_bar)
    recovered_ledger = SleeveLedger(horizon=derive_horizon(("1D",)))
    uninterrupted_ledger = SleeveLedger(horizon=derive_horizon(("1D",)))
    recovered = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(market_bars),
        book=book,
        ledger=recovered_ledger,
        arrays=SleeveArrays.bar_only(),
    )
    uninterrupted = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(market_bars),
        book=book,
        ledger=uninterrupted_ledger,
        arrays=SleeveArrays.bar_only(),
    )
    resolver = DeclaredMarkingResolver()
    market_clock = BookMarketClock(
        book=book,
        bar_type_resolver=resolver,
    )
    fast_forward = StartupFastForward(
        book=book,
        pipeline=recovered,
        roll_desk=None,
        bar_type_resolver=resolver,
        book_market_clock=market_clock,
        fx_reference_pairs=(),
    )
    loading = _require_recovering(fast_forward.begin(through=_THROUGH))
    request = loading.requests[0]
    ready = _complete_cash_history(fast_forward, request, history)

    uninterrupted_result = _process_market_history(
        uninterrupted, request.bar_type.instrument_id, history, live_bar
    )
    recovered_result = _process_next_market_bar(
        recovered, request.bar_type.instrument_id, history[-1], live_bar
    )
    market_clock.advance(request.bar_type, live_bar.ts_event)
    live_due = market_clock.drain()

    assert isinstance(ready, Ready)
    assert recovered_result.orders == uninterrupted_result.orders
    assert recovered.last_sleeve_weights == uninterrupted.last_sleeve_weights
    assert live_due == (
        DueSleeve(
            sleeve=_SLEEVE,
            period=CompletedRebalancePeriod(period=20_288, period_ns=_DAY_NS),
        ),
    )
    recovered_covariance = recovered_ledger.realized_covariance(
        (_SLEEVE,), min_returns=2
    )
    assert recovered_covariance is not None
    assert recovered_covariance == uninterrupted_ledger.realized_covariance(
        (_SLEEVE,), min_returns=2
    )


def _fast_forward() -> tuple[StartupFastForward, RebalancePipeline]:
    fast_forward, pipeline, _market_clock = _fast_forward_with_clock()
    return fast_forward, pipeline


def _require_recovering(update: RecoveryUpdate) -> Recovering:
    if not isinstance(update, Recovering):
        raise AssertionError(f"expected Recovering, got {update!r}")
    return update


def _fast_forward_with_clock() -> tuple[
    StartupFastForward,
    RebalancePipeline,
    BookMarketClock,
]:
    book_config = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_SLEEVE,
                wheel_filename="trend.whl",
                risk_share=1.0,
            ),
        ),
        base_currency="EUR",
    )
    book = assemble_test_book(
        book_config,
        {
            "trend.whl": _FixedBundle(
                make_bundle(native_instrument_ids=(_INSTRUMENT,), lookback_bars=1)
            )
        },
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=book,
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=SleeveArrays.bar_only(),
    )
    resolver = DeclaredMarkingResolver()
    market_clock = BookMarketClock(
        book=book,
        bar_type_resolver=resolver,
    )
    return (
        StartupFastForward(
            book=book,
            pipeline=pipeline,
            roll_desk=None,
            bar_type_resolver=resolver,
            book_market_clock=market_clock,
            fx_reference_pairs=(),
        ),
        pipeline,
        market_clock,
    )


def _bar(bar_type: BarType, timestamp_ns: int, close: float) -> Bar:
    price = Price.from_str(f"{close:.2f}")
    return Bar(
        bar_type,
        price,
        price,
        price,
        price,
        Quantity.from_int(1_000),
        timestamp_ns,
        timestamp_ns,
    )


def _due_request(period_start_ns: int, timestamp_ns: int) -> RebalanceRequest:
    return RebalanceRequest(
        due=(
            DueSleeve(
                sleeve=_SLEEVE,
                period=CompletedRebalancePeriod(
                    period=period_start_ns // _DAY_NS,
                    period_ns=_DAY_NS,
                ),
            ),
        ),
        timestamp_ns=timestamp_ns,
    )


def _complete_cash_history(
    fast_forward: StartupFastForward,
    request: Any,
    history: Sequence[MarketBar],
) -> RecoveryUpdate:
    for bar in history:
        fast_forward.receive_history(_bar(request.bar_type, bar.ts_event, bar.close))
    return fast_forward.history_loaded(request.key)


def _process_market_history(
    pipeline: RebalancePipeline,
    instrument_id: InstrumentId,
    history: Sequence[MarketBar],
    live_bar: MarketBar,
) -> RebalanceResult:
    pipeline.record_market_observation(
        history[0].ts_event, {instrument_id: history[0].close}
    )
    for previous, bar in zip(history[:-1], history[1:], strict=True):
        pipeline.record_market_observation(bar.ts_event, {instrument_id: bar.close})
        pipeline.rebalance(_due_request(previous.ts_event, bar.ts_event + 1))
    return _process_next_market_bar(pipeline, instrument_id, history[-1], live_bar)


def _process_next_market_bar(
    pipeline: RebalancePipeline,
    instrument_id: InstrumentId,
    previous: MarketBar,
    bar: MarketBar,
) -> RebalanceResult:
    pipeline.record_market_observation(bar.ts_event, {instrument_id: bar.close})
    return pipeline.rebalance(_due_request(previous.ts_event, bar.ts_event + 1))


def _recover_futures_without(omitted: InstrumentId) -> RecoveryUpdate:
    port, native = es_port_two_rolls()
    filtered_port = CatalogBackedDataPort(
        FakeCatalog(
            port.catalog.instruments(),
            {
                str(bars[0].bar_type): bars
                for instrument_id, bars in native.items()
                if instrument_id != omitted
            },
        )
    )
    fast_forward, _roll_desk, _book = _futures_fast_forward(filtered_port)
    loading = fast_forward.begin(through=datetime(2024, 7, 1, tzinfo=timezone.utc))
    if not isinstance(loading, Recovering):
        return loading
    return _complete_futures_history(
        fast_forward,
        loading,
        native,
        omitted=frozenset({omitted}),
    )


def _recover_two_streams(
    *,
    reverse_delivery: bool,
) -> tuple[Ready, RebalanceResult, dict[SleeveName, float]]:
    book = assemble_test_book(
        BookConfig(
            sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
            base_currency="EUR",
        ),
        {
            "trend.whl": _FixedBundle(
                make_bundle(
                    native_instrument_ids=(_INSTRUMENT, _WEEKLY_INSTRUMENT),
                    lookback_bars=1,
                )
            )
        },
    )
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(
            (
                _market_bar(_FIRST_NS, 100.0),
                _market_bar(_SECOND_NS, 101.0),
                _market_bar(_THIRD_NS, 102.0),
            )
        ),
        book=book,
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=SleeveArrays.bar_only(),
    )
    resolver = DeclaredMarkingResolver()
    fast_forward = StartupFastForward(
        book=book,
        pipeline=pipeline,
        roll_desk=None,
        bar_type_resolver=resolver,
        book_market_clock=BookMarketClock(
            book=book,
            bar_type_resolver=resolver,
        ),
        fx_reference_pairs=(),
    )
    loading = fast_forward.begin(through=_THROUGH)
    if not isinstance(loading, Recovering):
        raise AssertionError(f"expected Recovering, got {loading!r}")
    requests = loading.requests[::-1] if reverse_delivery else loading.requests
    outcome: RecoveryUpdate = loading
    for request in requests:
        bars = (
            _bar(request.bar_type, _FIRST_NS, 100.0),
            _bar(request.bar_type, _SECOND_NS, 101.0),
        )
        delivered = bars[::-1] if reverse_delivery else bars
        for bar in delivered:
            fast_forward.receive_history(bar)
        if reverse_delivery:
            fast_forward.receive_history(delivered[0])
        outcome = fast_forward.history_loaded(request.key)
    if not isinstance(outcome, Ready):
        raise AssertionError(f"expected Ready, got {outcome!r}")
    marks = {_INSTRUMENT: 102.0, _WEEKLY_INSTRUMENT: 102.0}
    pipeline.record_market_observation(_THIRD_NS, marks)
    result = pipeline.rebalance(_due_request(_SECOND_NS, _THIRD_NS + 1))
    return outcome, result, pipeline.last_sleeve_weights


def _futures_fast_forward(port: Any) -> tuple[StartupFastForward, RollDesk, Any]:
    roll_desk = RollDesk(
        catalog_port=port,
        instrument_present={_ESU4}.__contains__,
    )
    book = assemble_test_book(
        BookConfig(
            sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
            base_currency="EUR",
        ),
        {
            "trend.whl": _FixedBundle(
                make_bundle(
                    native_instrument_ids=(),
                    continuous_futures={"ES": _ES},
                    adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
                    lookback_bars=80,
                )
            )
        },
    )
    resolver = DeclaredMarkingResolver()
    fast_forward = StartupFastForward(
        book=book,
        pipeline=RebalancePipeline(
            book_state=_BookState(),
            market_data=_MarketData(),
            book=book,
            ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
            arrays=SleeveArrays.bar_only(),
        ),
        roll_desk=roll_desk,
        bar_type_resolver=resolver,
        book_market_clock=BookMarketClock(
            book=book,
            bar_type_resolver=resolver,
        ),
        fx_reference_pairs=(),
    )
    return fast_forward, roll_desk, book


def _complete_futures_history(
    fast_forward: StartupFastForward,
    loading: Recovering,
    native: Mapping[InstrumentId, Sequence[Bar]],
    *,
    omitted: frozenset[InstrumentId] = frozenset(),
) -> RecoveryUpdate:
    outcome: RecoveryUpdate = loading
    for request in loading.requests:
        if request.bar_type.instrument_id not in omitted:
            for bar in native[request.bar_type.instrument_id]:
                if _within_request(bar, request):
                    fast_forward.receive_history(bar)
        outcome = fast_forward.history_loaded(request.key)
    return outcome


def _process_uninterrupted_futures(
    port: Any,
    book: Any,
    loading: Recovering,
    native: Mapping[InstrumentId, Sequence[Bar]],
) -> RollDesk:
    bars = _requested_futures_bars(loading, native)
    first_event = datetime.fromtimestamp(
        bars[0].ts_event / 1_000_000_000,
        tz=timezone.utc,
    )
    desk = RollDesk(catalog_port=port, instrument_present={_ESU4}.__contains__)
    desk.start(
        end=first_event,
        warmup=False,
        declarations=book.continuous_declarations,
        history_starts={"ES": first_event},
    )
    bars_by_timestamp: dict[int, list[Bar]] = {}
    for bar in bars:
        bars_by_timestamp.setdefault(bar.ts_event, []).append(bar)
    for timestamp_ns in sorted(bars_by_timestamp):
        if timestamp_ns <= bars[0].ts_event:
            continue
        front = desk.front_leg(_ES)
        front_bar = next(
            (
                bar
                for bar in bars_by_timestamp[timestamp_ns]
                if bar.bar_type.instrument_id == front
            ),
            None,
        )
        if front_bar is not None:
            desk.on_bar(front_bar)
    return desk


def _requested_futures_bars(
    loading: Recovering,
    native: Mapping[InstrumentId, Sequence[Bar]],
) -> tuple[Bar, ...]:
    return tuple(
        sorted(
            {
                (bar.bar_type, bar.ts_event): bar
                for request in loading.requests
                for bar in native[request.bar_type.instrument_id]
                if _within_request(bar, request)
            }.values(),
            key=lambda bar: (bar.ts_event, str(bar.bar_type)),
        )
    )


def _history_through(
    native: Mapping[InstrumentId, Sequence[Bar]],
    through: datetime,
) -> dict[InstrumentId, tuple[Bar, ...]]:
    through_ns = int(through.timestamp() * 1_000_000_000)
    return {
        instrument_id: tuple(bar for bar in bars if bar.ts_event <= through_ns)
        for instrument_id, bars in native.items()
    }


def _within_request(bar: Bar, request: Any) -> bool:
    return (
        int(request.start.timestamp() * 1_000_000_000)
        <= bar.ts_event
        <= int(request.end.timestamp() * 1_000_000_000)
    )


def _market_bar(timestamp_ns: int, close: float) -> MarketBar:
    return MarketBar(timestamp_ns, close, close, close, close, 1_000.0)
