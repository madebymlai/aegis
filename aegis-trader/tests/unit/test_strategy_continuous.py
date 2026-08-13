"""Strategy relay tests for Roll Desk intent batches."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_runtime.domain.rebasing import spread_rebasing
from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import CatalogBackedDataPort
from aegis_data.marking import DeclaredMarkingResolver
from aegis_data.raw_bars import RawBars
from aegis_data.storage import Catalog, CatalogInterval
from aegis_data.testing import es_port_two_rolls
from aegis_trader.bundles.book import ContinuousRootDeclaration
from aegis_trader.domain.roll import (
    Halt,
    RequestBars,
    RequestInstrument,
    RollEvent,
    SubscribeBars,
    UnsubscribeBars,
)
from aegis_trader.domain.startup import StartupGate, StartupResult
from aegis_trader.domain.types import OrderIntent, OrderSide, OrderSource, SleeveName
from aegis_trader.trader.book_startup import SubscribeQuoteTicks
from aegis_trader.trader.bar_capture import BarCapture
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    DueSleeve,
    GateOutcome,
    RebalanceRequest,
    RebalanceResult,
    RebalanceSummary,
)
from aegis_trader.trader.strategy import RebalanceStrategy
from aegis_trader.trader.roll_desk import RollDesk
from aegis_trader.trader.startup_fast_forward import (
    HistoryRequest,
    HistoryRequestKey,
    Ready,
    Recovering,
    RecoveryProgress,
    RECOVERY_TOPIC,
)

_ES = InstrumentId.from_str("ES.XCME")
_ESH4 = InstrumentId.from_str("ESH4.XCME")
_ESM4 = InstrumentId.from_str("ESM4.XCME")
_ESU4 = InstrumentId.from_str("ESU4.XCME")


class _FakePipeline:
    def __init__(self, applied: list[tuple[str, object]]) -> None:
        self.roll_events: list[RollEvent] = []
        self._applied = applied

    def apply_roll(self, event: RollEvent) -> None:
        self.roll_events.append(event)
        self._applied.append(("roll", event))


class _RelayHarness:
    _apply_boot_intents: Any = RebalanceStrategy._apply_boot_intents
    _apply_boot_intent: Any = RebalanceStrategy._apply_boot_intent
    _apply_roll_intents: Any = RebalanceStrategy._apply_roll_intents
    _apply_roll_intent: Any = RebalanceStrategy._apply_roll_intent
    _halt_from_roll_intent: Any = RebalanceStrategy._halt_from_roll_intent
    _require_pipeline: Any = RebalanceStrategy._require_pipeline
    _mark_bars: Any = RebalanceStrategy._mark_bars

    def __init__(self) -> None:
        self._bar_type_resolver = DeclaredMarkingResolver()
        self._bar_capture = None
        self.applied: list[tuple[str, object]] = []
        self._pipeline = _FakePipeline(self.applied)
        self._startup_result: StartupResult | None = None
        self._is_halted = False
        self.subscribed: list[object] = []
        self.unsubscribed: list[object] = []
        self.requested_instruments: list[InstrumentId] = []
        self.requested_bars: list[dict[str, object]] = []
        self.subscribed_quote_ticks: list[InstrumentId] = []
        self.logged_halts: list[StartupResult] = []

    def subscribe_bars(self, bar_type: object) -> None:
        self.subscribed.append(bar_type)
        self.applied.append(("subscribe", bar_type))

    def unsubscribe_bars(self, bar_type: object) -> None:
        self.unsubscribed.append(bar_type)
        self.applied.append(("unsubscribe", bar_type))

    def request_instrument(self, instrument_id: InstrumentId) -> None:
        self.requested_instruments.append(instrument_id)
        self.applied.append(("request_instrument", instrument_id))

    def request_bars(self, bar_type: object, **kwargs: object) -> None:
        self.requested_bars.append({"bar_type": bar_type, **kwargs})
        self.applied.append(("request_bars", bar_type))

    def subscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        self.subscribed_quote_ticks.append(instrument_id)
        self.applied.append(("subscribe_quote_ticks", instrument_id))

    def _log_startup_halt(self, result: StartupResult) -> None:
        self.logged_halts.append(result)

    @property
    def startup_result(self) -> StartupResult | None:
        return self._startup_result


def test_strategy_does_not_expose_mutable_ledger() -> None:
    exposes_mutable_ledger = hasattr(RebalanceStrategy, "sleeve_ledger")

    assert exposes_mutable_ledger is False


def test_roll_relay_applies_subscription_warmup_and_roll_intents_in_order() -> None:
    old_front = InstrumentId.from_str("ESM4.XCME")
    new_front = InstrumentId.from_str("ESU4.XCME")
    continuous_id = InstrumentId.from_str("ES.XCME")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 5, tzinfo=timezone.utc)
    harness = _RelayHarness()

    halted = harness._apply_roll_intents(
        (
            UnsubscribeBars(old_front, "1D"),
            RequestInstrument(new_front),
            RequestBars(new_front, "1D", start, end),
            SubscribeBars(new_front, "1D"),
            RollEvent(continuous_id, spread_rebasing(5.0)),
        )
    )

    assert halted is False
    assert harness.applied == [
        ("unsubscribe", raw_bar_type(old_front, "1D")),
        ("request_instrument", new_front),
        ("request_bars", raw_bar_type(new_front, "1D")),
        ("subscribe", raw_bar_type(new_front, "1D")),
        ("roll", RollEvent(continuous_id, spread_rebasing(5.0))),
    ]


def test_roll_relay_turns_halt_intent_into_startup_halt() -> None:
    harness = _RelayHarness()
    expected = StartupResult(
        trading_enabled=False,
        halt_gate=StartupGate.CONTINUOUS_IDENTITY,
        halt_reason="venue mismatch",
    )

    halted = harness._apply_roll_intents(
        (Halt(StartupGate.CONTINUOUS_IDENTITY, "venue mismatch"),)
    )

    assert halted is True
    assert harness.startup_result == expected
    assert harness.logged_halts == [expected]


def test_boot_relay_applies_bar_and_quote_subscriptions_in_order() -> None:
    native = InstrumentId.from_str("VUSA.XLON")
    quote = InstrumentId.from_str("EUR/USD.IDEALPRO")
    harness = _RelayHarness()

    halted = harness._apply_boot_intents(
        (
            SubscribeBars(native, "1D"),
            SubscribeQuoteTicks(quote),
        )
    )

    assert halted is False
    assert harness.applied == [
        ("subscribe", raw_bar_type(native, "1D")),
        ("subscribe_quote_ticks", quote),
    ]


class _Recovery:
    def __init__(self) -> None:
        self.loaded: list[HistoryRequestKey] = []

    def history_loaded(self, key: HistoryRequestKey) -> Recovering:
        self.loaded.append(key)
        return Recovering((), RecoveryProgress(1, 2, 3, None))


class _RecoveryRelayHarness:
    _handle_recovery: Any = RebalanceStrategy._handle_recovery
    _request_recovery_history: Any = RebalanceStrategy._request_recovery_history

    def __init__(self) -> None:
        self._fast_forward = _Recovery()
        self.requested_bars: list[dict[str, object]] = []
        self.published: list[tuple[str, object, bool]] = []
        self.msgbus = SimpleNamespace(
            publish=lambda topic, msg, external_pub: self.published.append(
                (topic, msg, external_pub)
            )
        )

    def request_bars(self, bar_type: object, **kwargs: object) -> None:
        self.requested_bars.append({"bar_type": bar_type, **kwargs})


class _BoundaryDesk:
    def __init__(self) -> None:
        self.bars: list[Bar] = []

    def continuous_id(self, _instrument_id: InstrumentId) -> None:
        return None

    def on_bar(self, bar: Bar) -> tuple[()]:
        self.bars.append(bar)
        return ()


class _FakeBookMarketClock:
    def __init__(self, due: tuple[DueSleeve, ...] = ()) -> None:
        self.advances: list[tuple[BarType, int, InstrumentId | None]] = []
        self.due = due

    def advance(
        self,
        bar_type: BarType,
        timestamp_ns: int,
        *,
        continuous_id: InstrumentId | None = None,
    ) -> None:
        self.advances.append((bar_type, timestamp_ns, continuous_id))

    @property
    def has_pending_due(self) -> bool:
        return bool(self.due)

    def drain(self) -> tuple[DueSleeve, ...]:
        due = self.due
        self.due = ()
        return due


class _AlertClock:
    def __init__(self) -> None:
        self.alerts: list[tuple[str, int, object]] = []

    def set_time_alert_ns(
        self,
        name: str,
        timestamp_ns: int,
        *,
        callback: object,
    ) -> None:
        self.alerts.append((name, timestamp_ns, callback))


class _AllBookStreams(dict[BarType, str]):
    def __contains__(self, _key: object) -> bool:
        return True


class _ReNetPipeline:
    def __init__(self) -> None:
        self.requests: list[RebalanceRequest] = []
        self.last_sleeve_weights: dict[SleeveName, float] = {}

    def rebalance(self, request: RebalanceRequest) -> RebalanceResult:
        self.requests.append(request)
        return RebalanceResult(
            orders=(),
            summary=RebalanceSummary(
                nav=100_000.0,
                num_sleeves=0,
                num_targets=0,
                num_orders=0,
                gate_outcome=GateOutcome.PASS,
                total_notional=0.0,
            ),
        )


def _fire_alert(callback: object, *, ts_event: int) -> None:
    if not callable(callback):
        raise AssertionError(f"expected an alert callback, got {callback!r}")
    callback(SimpleNamespace(ts_event=ts_event))


class _BoundaryHarness:
    on_bar: Any = RebalanceStrategy.on_bar
    _schedule_re_net: Any = RebalanceStrategy._schedule_re_net
    _on_re_net_alert: Any = RebalanceStrategy._on_re_net_alert
    _rebalance_due_sleeves: Any = RebalanceStrategy._rebalance_due_sleeves
    _require_pipeline: Any = RebalanceStrategy._require_pipeline

    def __init__(
        self,
        ready: Ready,
        *,
        due: tuple[DueSleeve, ...] = (),
    ) -> None:
        self._assembled_book = object()
        self._bar_capture = None
        self._is_halted = False
        self._is_recovering = False
        self._recovery_ready = ready
        self._stream_watermarks = {
            bar.bar_type: bar.ts_event for bar in ready.boundary_bars
        }
        self._book_activity = ready.book_activity
        self._desk = _BoundaryDesk()
        self._book_market_clock = _FakeBookMarketClock(due)
        self._timeframe_by_bar_type: dict[BarType, str] = _AllBookStreams()
        self._pending_due_timestamp: int | None = None
        self._pipeline = _ReNetPipeline()
        self._last_sleeve_weights: dict[SleeveName, float] = {}
        self.clock = _AlertClock()
        self.observed: list[Bar] = []
        self.halts: list[Halt] = []

    def _require_roll_desk(self) -> _BoundaryDesk:
        return self._desk

    def _apply_roll_intents(self, _intents: object) -> bool:
        return False

    def _resolve_derived_mark(self, _bar: Bar) -> None:
        return None

    def _record_market_observation(
        self,
        bar: Bar,
        _derived_mark: object,
        _continuous_id: object,
    ) -> None:
        self.observed.append(bar)

    def _require_book_market_clock(self) -> _FakeBookMarketClock:
        return self._book_market_clock

    def _halt_from_roll_intent(self, halt: Halt) -> None:
        self.halts.append(halt)
        self._is_halted = True


def test_recovery_relay_pairs_each_history_request_with_its_callback() -> None:
    harness = _RecoveryRelayHarness()
    instrument_id = InstrumentId.from_str("VUSA.XLON")
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    end = datetime(2026, 7, 18, tzinfo=timezone.utc)
    request = HistoryRequest(
        HistoryRequestKey(7),
        raw_bar_type(instrument_id, "1D"),
        start,
        end,
    )

    update = Recovering((request,), RecoveryProgress(0, 1, 0, None))
    harness._handle_recovery(update)
    callback = harness.requested_bars[0]["callback"]
    assert callable(callback)
    callback(object())

    assert harness.requested_bars[0] == {
        "bar_type": raw_bar_type(instrument_id, "1D"),
        "start": start,
        "end": end,
        "callback": callback,
        "update_catalog": True,
    }
    assert harness._fast_forward.loaded == [HistoryRequestKey(7)]
    assert harness.published[0] == (RECOVERY_TOPIC, update, False)


def test_strategy_processes_the_first_live_bar_exactly_once_after_recovery() -> None:
    instrument_id = InstrumentId.from_str("VUSA.XLON")
    bar_type = raw_bar_type(instrument_id, "1D")
    boundary = _bar(bar_type, 1_000, 100.0)
    live = _bar(bar_type, 2_000, 101.0)
    harness = _BoundaryHarness(
        Ready((), boundary.ts_event, (boundary,), StartupResult(True))
    )

    harness.on_bar(live)
    harness.on_bar(live)

    assert harness.observed == [live]
    assert harness._desk.bars == [live]
    assert harness._book_market_clock.advances == [(bar_type, live.ts_event, None)]
    assert harness.clock.alerts == []
    assert harness.halts == []


def test_strategy_keeps_a_non_front_roll_probe_out_of_book_observations() -> None:
    candidate_type = raw_bar_type(InstrumentId.from_str("ESU4.XCME"), "1D")
    candidate = _bar(candidate_type, 2_000, 202.0)
    harness = _BoundaryHarness(Ready((), None, (), StartupResult(True)))
    harness._timeframe_by_bar_type = {}

    harness.on_bar(candidate)

    assert harness._desk.bars == [candidate]
    assert harness.observed == []
    assert harness._book_market_clock.advances == []
    assert harness._stream_watermarks[candidate_type] == candidate.ts_event


def test_strategy_bar_handler_crosses_a_session_boundary_with_silent_candidates(
    tmp_path: Path,
) -> None:
    history_start = datetime(2024, 1, 15, tzinfo=timezone.utc)
    startup = datetime(2024, 5, 10, tzinfo=timezone.utc)
    startup_ns = pd.Timestamp(startup).value
    source, native = es_port_two_rolls()
    catalog = Catalog.open(tmp_path / "catalog")
    raw_bars = _seed_roll_catalog(
        catalog,
        source,
        native,
        history_start_ns=pd.Timestamp(history_start).value,
        startup_ns=startup_ns,
    )
    desk = RollDesk(
        catalog_port=CatalogBackedDataPort(catalog),
        instrument_present=lambda _instrument_id: True,
    )
    subscriptions = desk.start(
        history_starts={"ES": history_start},
        end=startup,
        warmup=False,
        declarations={
            "ES": ContinuousRootDeclaration(
                continuous_id=_ES,
                adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
                timeframe="1D",
            )
        },
    )
    capture = BarCapture(raw_bars)
    _subscribe_capture(capture, subscriptions, at_ns=startup_ns)
    next_front_bar = _native_bar_on(native, _ESM4, date(2024, 5, 13))
    harness = _BoundaryHarness(Ready((), None, (), StartupResult(True)))
    harness._desk = desk
    harness._bar_capture = capture

    harness.on_bar(next_front_bar)

    assert harness.observed == [next_front_bar]


def test_strategy_bar_handler_admits_every_stream_that_closed_on_one_session(
    tmp_path: Path,
) -> None:
    """The Book marks many instruments; their daily closes share one instant.

    Nautilus stamps a DAY-aggregated Bar at its UTC close, so a commingled Book
    delivers several Bars carrying the identical ``ts_event``, one after the
    other. None of them is evidence about the others.
    """
    catalog = Catalog.open(tmp_path / "catalog")
    raw_bars = RawBars(catalog)
    capture = BarCapture(raw_bars)
    first = raw_bar_type(InstrumentId.from_str("VUSA.XLON"), "1D")
    second = raw_bar_type(InstrumentId.from_str("AAPL.XNAS"), "1D")
    subscribed_at = pd.Timestamp("2024-01-04", tz="UTC").value
    close = pd.Timestamp("2024-01-05", tz="UTC").value
    for bar_type in (first, second):
        capture.subscribe(bar_type, at_ns=subscribed_at)
    harness = _BoundaryHarness(Ready((), None, (), StartupResult(True)))
    harness._bar_capture = capture

    harness.on_bar(_bar(first, close, 100.0))
    harness.on_bar(_bar(second, close, 200.0))

    assert [bar.close.as_double() for bar in harness.observed] == [100.0, 200.0]


def _seed_roll_catalog(
    catalog: Catalog,
    source: CatalogBackedDataPort,
    native: dict[InstrumentId, list[Bar]],
    *,
    history_start_ns: int,
    startup_ns: int,
) -> RawBars:
    leg_ids = (_ESH4, _ESM4, _ESU4)
    catalog.store_definitions(source.catalog.definitions(leg_ids))
    raw_bars = RawBars(catalog)
    for instrument_id in leg_ids:
        bar_type = raw_bar_type(instrument_id, "1D")
        raw_bars.record_verified(
            bar_type,
            CatalogInterval(history_start_ns, startup_ns),
            tuple(bar for bar in native[instrument_id] if bar.ts_event <= startup_ns),
        )
    return raw_bars


def _subscribe_capture(
    capture: BarCapture,
    subscriptions: tuple[object, ...],
    *,
    at_ns: int,
) -> None:
    for intent in subscriptions:
        if not isinstance(intent, SubscribeBars):
            raise AssertionError(f"expected subscription, got {intent!r}")
        capture.subscribe(
            raw_bar_type(intent.instrument_id, intent.timeframe),
            at_ns=at_ns,
        )


def _native_bar_on(
    native: dict[InstrumentId, list[Bar]],
    instrument_id: InstrumentId,
    day: date,
) -> Bar:
    return next(
        bar
        for bar in native[instrument_id]
        if pd.Timestamp(bar.ts_event, tz="UTC").date() == day
    )


def test_strategy_halts_a_conflicting_recovery_boundary_bar() -> None:
    instrument_id = InstrumentId.from_str("VUSA.XLON")
    bar_type = raw_bar_type(instrument_id, "1D")
    boundary = _bar(bar_type, 1_000, 100.0)
    conflict = _bar(bar_type, 1_000, 999.0)
    harness = _BoundaryHarness(
        Ready((), boundary.ts_event, (boundary,), StartupResult(True))
    )

    harness.on_bar(conflict)

    assert len(harness.halts) == 1
    assert harness.halts[0].gate == StartupGate.RECOVERY_HISTORY
    assert harness.observed == []


def test_strategy_arms_one_flush_for_all_due_bars_at_one_timestamp() -> None:
    first_type = raw_bar_type(InstrumentId.from_str("VUSA.XLON"), "1D")
    second_type = raw_bar_type(InstrumentId.from_str("SPY.ARCA"), "1D")
    due = (
        DueSleeve(
            sleeve=SleeveName("trend"),
            period=CompletedRebalancePeriod(period=7, period_ns=86_400_000_000_000),
        ),
    )
    harness = _BoundaryHarness(
        Ready((), None, (), StartupResult(True)),
        due=due,
    )

    harness.on_bar(_bar(first_type, 2_000, 101.0))
    harness.on_bar(_bar(second_type, 2_000, 202.0))

    assert len(harness.clock.alerts) == 1
    assert harness.clock.alerts[0][:2] == ("re-net-2000", 2_001)


def test_strategy_flushes_the_coalesced_due_set_as_one_book_re_net() -> None:
    bar_type = raw_bar_type(InstrumentId.from_str("VUSA.XLON"), "1D")
    due = (
        DueSleeve(
            sleeve=SleeveName("trend"),
            period=CompletedRebalancePeriod(period=7, period_ns=86_400_000_000_000),
        ),
    )
    harness = _BoundaryHarness(
        Ready((), None, (), StartupResult(True)),
        due=due,
    )
    harness.on_bar(_bar(bar_type, 2_000, 101.0))
    callback = harness.clock.alerts[0][2]

    _fire_alert(callback, ts_event=2_001)

    assert harness._pipeline.requests == [
        RebalanceRequest(due=due, timestamp_ns=2_001)
    ]
    assert harness._book_market_clock.has_pending_due is False


def test_halted_strategy_drains_due_sleeves_without_rebalancing() -> None:
    bar_type = raw_bar_type(InstrumentId.from_str("VUSA.XLON"), "1D")
    due = (
        DueSleeve(
            sleeve=SleeveName("trend"),
            period=CompletedRebalancePeriod(period=7, period_ns=86_400_000_000_000),
        ),
    )
    harness = _BoundaryHarness(
        Ready((), None, (), StartupResult(True)),
        due=due,
    )
    harness.on_bar(_bar(bar_type, 2_000, 101.0))
    callback = harness.clock.alerts[0][2]
    harness._is_halted = True

    _fire_alert(callback, ts_event=2_001)

    assert harness._book_market_clock.has_pending_due is False
    assert harness._pipeline.requests == []


class _FakeMarketData:
    def __init__(
        self,
        front_by_root: dict[InstrumentId, InstrumentId],
        qty: Quantity,
        *,
        missing_ids: frozenset[InstrumentId] = frozenset(),
    ) -> None:
        self._front_by_root = front_by_root
        self._qty = qty
        self._missing_ids = missing_ids

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        return self._front_by_root.get(instrument_id, instrument_id)

    def make_quantity(
        self, instrument_id: InstrumentId, _raw_shares: float
    ) -> Quantity | None:
        return None if instrument_id in self._missing_ids else self._qty


class _SubmitHarness:
    _submit_order_intents: Any = RebalanceStrategy._submit_order_intents
    _materialize_order_intent: Any = RebalanceStrategy._materialize_order_intent
    _require_market_data: Any = RebalanceStrategy._require_market_data

    def __init__(self, market_data: _FakeMarketData) -> None:
        self._market_data = market_data
        self._is_halted = False
        self.config = SimpleNamespace(fill_time_in_force=None)
        self.errors: list[str] = []
        self.log = SimpleNamespace(error=self.errors.append, info=lambda *a: None)
        self.order_factory = SimpleNamespace(market=lambda **kwargs: kwargs)
        self.submitted: list[dict[str, object]] = []

    def submit_order(self, order: dict[str, object]) -> None:
        self.submitted.append(order)


def test_submit_order_intent_routes_a_continuous_root_to_the_front_leg() -> None:
    cont = InstrumentId.from_str("ES.XCME")
    front = InstrumentId.from_str("ESM4.XCME")
    qty = Quantity.from_int(3)
    harness = _SubmitHarness(_FakeMarketData({cont: front}, qty))

    harness._submit_order_intents(
        (
            OrderIntent(
                instrument_id=cont,
                side=OrderSide.BUY,
                quantity=3.0,
                source=OrderSource.ALPHA,
            ),
        )
    )

    order = harness.submitted[0]
    assert order["instrument_id"] == front
    assert order["quantity"] == qty


def test_submit_order_intent_leaves_a_native_instrument_untouched() -> None:
    native = InstrumentId.from_str("VUSA.XLON")
    qty = Quantity.from_int(5)
    harness = _SubmitHarness(_FakeMarketData({}, qty))

    harness._submit_order_intents(
        (
            OrderIntent(
                instrument_id=native,
                side=OrderSide.SELL,
                quantity=5.0,
                source=OrderSource.ALPHA,
            ),
        )
    )

    assert harness.submitted[0]["instrument_id"] == native
    assert harness.submitted[0]["quantity"] == qty


def test_submit_order_intents_halts_before_partial_submission_when_quantity_is_missing() -> (
    None
):
    available = InstrumentId.from_str("VUSA.XLON")
    missing = InstrumentId.from_str("MISSING.XLON")
    harness = _SubmitHarness(
        _FakeMarketData(
            {},
            Quantity.from_int(5),
            missing_ids=frozenset({missing}),
        )
    )

    harness._submit_order_intents(
        (
            OrderIntent(available, OrderSide.SELL, 5.0),
            OrderIntent(missing, OrderSide.SELL, 5.0),
        )
    )

    assert harness.submitted == []
    assert harness._is_halted is True
    assert harness.errors == [
        "Order materialization FAILED: instrument not found for InstrumentId "
        "MISSING.XLON. HALTING the book."
    ]


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
