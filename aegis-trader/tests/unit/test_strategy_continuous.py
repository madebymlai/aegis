"""Strategy relay tests for Roll Desk intent batches."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity

from aegis_data.rebasing import spread_rebasing
from aegis_trader.data import raw_bar_type
from aegis_trader.domain.roll import (
    Halt,
    RequestBars,
    RequestInstrument,
    RollEvent,
    SubscribeBars,
    UnsubscribeBars,
)
from aegis_trader.domain.startup import StartupGate, StartupResult
from aegis_trader.domain.types import OrderIntent, OrderSide, OrderSource
from aegis_trader.trader.book_startup import SubscribeQuoteTicks
from aegis_trader.trader.strategy import RebalanceStrategy


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

    def __init__(self) -> None:
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

    halted = harness._apply_roll_intents(
        (Halt(StartupGate.CONTINUOUS_IDENTITY, "venue mismatch"),)
    )

    assert halted is True
    assert harness._is_halted is True
    assert harness._startup_result == StartupResult(
        trading_enabled=False,
        halt_gate=StartupGate.CONTINUOUS_IDENTITY,
        halt_reason="venue mismatch",
    )
    assert harness.logged_halts == [harness._startup_result]


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


class _FakeMarketData:
    def __init__(self, front_by_root: dict[InstrumentId, InstrumentId], qty: Quantity) -> None:
        self._front_by_root = front_by_root
        self._qty = qty

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        return self._front_by_root.get(instrument_id, instrument_id)

    def make_quantity(self, _instrument_id: InstrumentId, _raw_shares: float) -> Quantity:
        return self._qty


class _SubmitHarness:
    _submit_order_intent: Any = RebalanceStrategy._submit_order_intent
    _require_market_data: Any = RebalanceStrategy._require_market_data

    def __init__(self, market_data: _FakeMarketData) -> None:
        self._market_data = market_data
        self.config = SimpleNamespace(fill_time_in_force=None)
        self.log = SimpleNamespace(error=lambda *a: None, info=lambda *a: None)
        self.order_factory = SimpleNamespace(market=lambda **kwargs: kwargs)
        self.submitted: list[dict[str, object]] = []

    def submit_order(self, order: dict[str, object]) -> None:
        self.submitted.append(order)


def test_submit_order_intent_routes_a_continuous_root_to_the_front_leg() -> None:
    cont = InstrumentId.from_str("ES.XCME")
    front = InstrumentId.from_str("ESM4.XCME")
    qty = Quantity.from_int(3)
    harness = _SubmitHarness(_FakeMarketData({cont: front}, qty))

    harness._submit_order_intent(
        OrderIntent(
            instrument_id=cont,
            side=OrderSide.BUY,
            quantity=3.0,
            source=OrderSource.ALPHA,
        )
    )

    order = harness.submitted[0]
    assert order["instrument_id"] == front
    assert order["quantity"] == qty


def test_submit_order_intent_leaves_a_native_instrument_untouched() -> None:
    native = InstrumentId.from_str("VUSA.XLON")
    qty = Quantity.from_int(5)
    harness = _SubmitHarness(_FakeMarketData({}, qty))

    harness._submit_order_intent(
        OrderIntent(
            instrument_id=native,
            side=OrderSide.SELL,
            quantity=5.0,
            source=OrderSource.ALPHA,
        )
    )

    assert harness.submitted[0]["instrument_id"] == native
