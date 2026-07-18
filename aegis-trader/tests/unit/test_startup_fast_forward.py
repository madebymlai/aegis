from __future__ import annotations

from datetime import datetime, timezone

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.marking import DeclaredMarkingResolver, MarkMode
from aegis_data.testing import es_port_two_rolls
from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.analytics_horizon import derive_horizon
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.roll import Halt, SubscribeBars
from aegis_trader.domain.startup import StartupGate
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.pipeline import RebalancePipeline
from aegis_trader.trader.sleeve_arrays import SleeveArrays
from aegis_trader.trader.roll_desk import RollDesk
from aegis_trader.bundles.marking import RecordedMarkingResolver
from aegis_trader.trader.startup_fast_forward import (
    Ready,
    Recovering,
    StartupFastForward,
)
from tests.support.factories import assemble_test_book, make_bundle

_INSTRUMENT = InstrumentId.from_str("SPY.ARCA")
_WEEKLY_INSTRUMENT = InstrumentId.from_str("QQQ.NASDAQ")
_SLEEVE = SleeveName("trend")
_WEEKLY_SLEEVE = SleeveName("carry")
_DAY_NS = 86_400_000_000_000
_FIRST_NS = 1_752_710_400_000_000_000
_SECOND_NS = _FIRST_NS + _DAY_NS
_THROUGH = datetime(2025, 7, 19, tzinfo=timezone.utc)
_ES = InstrumentId.from_str("ES.XCME")
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
    def __init__(self) -> None:
        self._bars = (
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
        return self._bars[-limit:]

    def has_bar_in_period(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        return True


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
    assert pipeline.observation_count == 2


def test_fast_forward_leaves_the_live_clock_at_the_replayed_book_frontier() -> None:
    fast_forward, _pipeline = _fast_forward()
    loading = fast_forward.begin(through=_THROUGH)
    assert isinstance(loading, Recovering)
    request = loading.requests[0]
    fast_forward.receive_history(_bar(request.bar_type, _FIRST_NS, 100.0))
    fast_forward.receive_history(_bar(request.bar_type, _SECOND_NS, 101.0))
    ready = fast_forward.history_loaded(request.key)

    assert isinstance(ready, Ready)
    assert dict(ready.resume_periods) == {_SLEEVE: _SECOND_NS // _DAY_NS}


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
            "trend.whl": make_bundle(
                native_instrument_ids=(),
                continuous_futures={"ES": _ES},
                adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
                lookback_bars=80,
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
        fx_reference_pairs=(),
    )
    loading = fast_forward.begin(through=datetime(2024, 7, 1, tzinfo=timezone.utc))
    assert isinstance(loading, Recovering)

    bars_by_instrument = native
    for request in loading.requests:
        for bar in bars_by_instrument[request.bar_type.instrument_id]:
            if (
                request.start.timestamp() * 1_000_000_000
                <= bar.ts_event
                <= request.end.timestamp() * 1_000_000_000
            ):
                fast_forward.receive_history(bar)
        outcome = fast_forward.history_loaded(request.key)

    assert isinstance(outcome, Ready)
    assert {request.bar_type.instrument_id for request in loading.requests} == set(
        native
    )
    assert outcome.intents == (SubscribeBars(_ESU4, "1D"),)
    assert roll_desk.front_leg(_ES) == _ESU4


def test_fast_forward_halts_when_quote_marking_sides_do_not_share_timestamps() -> None:
    book_config = BookConfig(
        sleeves=(SleeveConfig(_SLEEVE, "trend.whl", 1.0),),
        base_currency="EUR",
    )
    book = assemble_test_book(
        book_config,
        {
            "trend.whl": make_bundle(
                native_instrument_ids=(_INSTRUMENT,), lookback_bars=1
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
    fast_forward = StartupFastForward(
        book=book,
        pipeline=pipeline,
        roll_desk=None,
        bar_type_resolver=RecordedMarkingResolver(
            recorded={_INSTRUMENT: MarkMode.QUOTE}
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
            "trend.whl": make_bundle(
                native_instrument_ids=(_INSTRUMENT,), lookback_bars=1
            ),
            "carry.whl": make_bundle(
                native_instrument_ids=(_WEEKLY_INSTRUMENT,),
                timeframe="1W",
                lookback_bars=1,
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
    fast_forward = StartupFastForward(
        book=book,
        pipeline=pipeline,
        roll_desk=None,
        bar_type_resolver=resolver,
        fx_reference_pairs=(),
    )
    loading = fast_forward.begin(through=_THROUGH)
    assert isinstance(loading, Recovering)
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
    fast_forward.receive_history(
        _bar(weekly.bar_type, _SECOND_NS - 7 * _DAY_NS, 200.0)
    )
    fast_forward.receive_history(_bar(weekly.bar_type, _SECOND_NS, 201.0))

    one_loaded = fast_forward.history_loaded(daily.key)
    ready = fast_forward.history_loaded(weekly.key)

    assert isinstance(one_loaded, Recovering)
    assert isinstance(ready, Ready)
    assert dict(ready.resume_periods) == {
        _WEEKLY_SLEEVE: _SECOND_NS // (7 * _DAY_NS),
        _SLEEVE: _SECOND_NS // _DAY_NS,
    }


def _fast_forward() -> tuple[StartupFastForward, RebalancePipeline]:
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
            "trend.whl": make_bundle(
                native_instrument_ids=(_INSTRUMENT,), lookback_bars=1
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
    return (
        StartupFastForward(
            book=book,
            pipeline=pipeline,
            roll_desk=None,
            bar_type_resolver=resolver,
            fx_reference_pairs=(),
        ),
        pipeline,
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


def _market_bar(timestamp_ns: int, close: float) -> MarketBar:
    return MarketBar(timestamp_ns, close, close, close, close, 1_000.0)
