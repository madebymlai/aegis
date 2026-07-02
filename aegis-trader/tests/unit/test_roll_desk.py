"""Roll Desk unit tests: continuous-roll state in, typed intents out."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.domain.roll import (
    Halt,
    RequestBars,
    RequestInstrument,
    RollEvent,
    SubscribeBars,
    UnsubscribeBars,
)
from aegis_trader.domain.startup import StartupGate
from aegis_trader.trader.roll_desk import RollDesk
from test_continuous_feed import _es_port, _es_port_two_rolls

_HISTORY_START = datetime(2024, 1, 15, tzinfo=timezone.utc)
_ES = InstrumentId.from_str("ES.XCME")
_ES_IFUS = InstrumentId.from_str("ES.IFUS")
_ESH4 = InstrumentId.from_str("ESH4.XCME")
_ESM4 = InstrumentId.from_str("ESM4.XCME")
_ESU4 = InstrumentId.from_str("ESU4.XCME")


def _desk(port, *, present: tuple[InstrumentId, ...] = (), declared: InstrumentId = _ES) -> RollDesk:
    present_set = set(present)
    return RollDesk(
        catalog_port=port,
        instrument_present=present_set.__contains__,
        declared_continuous_ids_by_root={"ES": declared},
        timeframe="1D",
        history_start=_HISTORY_START,
    )


def _dt(day: str) -> datetime:
    return datetime.combine(pd.Timestamp(day).date(), datetime.min.time(), timezone.utc)


def _bar_on(native: dict[InstrumentId, list[Bar]], instrument_id: InstrumentId, day: date) -> Bar:
    return next(
        bar
        for bar in native[instrument_id]
        if pd.Timestamp(bar.ts_event, tz="UTC").date() == day
    )


def test_start_returns_front_leg_warmup_and_subscribe_intents() -> None:
    port, _native = _es_port()
    desk = _desk(port)

    intents = desk.start(end=_dt("2024-02-15"), warmup=True)

    assert intents == (
        RequestBars(_ESH4, "1D", _HISTORY_START, _dt("2024-02-15")),
        SubscribeBars(_ESH4, "1D"),
    )
    assert desk.front_leg(_ES) == _ESH4
    assert desk.series(_ES) is not None


def test_start_halts_when_materialized_continuous_venue_differs_from_declaration() -> None:
    port, _native = _es_port()
    desk = _desk(port, declared=_ES_IFUS)

    intents = desk.start(end=_dt("2024-02-15"), warmup=True)

    assert intents == (
        Halt(
            StartupGate.CONTINUOUS_IDENTITY,
            "continuous root 'ES' materialized as ES.XCME, expected ES.IFUS",
        ),
    )


def test_on_bar_without_a_roll_appends_offset_zero_and_emits_no_intents() -> None:
    port, native = _es_port_two_rolls()
    desk = _desk(port)
    desk.start(end=_dt("2024-05-10"), warmup=False)
    series_before = desk.series(_ES)
    bar = _bar_on(native, _ESM4, date(2024, 5, 13))

    intents = desk.on_bar(bar)

    series_after = desk.series(_ES)
    assert series_before is not None
    assert series_after is not None
    assert intents == ()
    assert len(series_after) == len(series_before) + 1


def test_on_bar_with_a_roll_returns_unsubscribe_ensure_new_and_roll_event() -> None:
    port, native = _es_port_two_rolls()
    desk = _desk(port)
    desk.start(end=_dt("2024-06-06"), warmup=False)
    bar = _bar_on(native, _ESM4, date(2024, 6, 14))

    intents = desk.on_bar(bar)

    assert intents[:2] == (
        UnsubscribeBars(_ESM4, "1D"),
        RequestInstrument(_ESU4),
    )
    assert isinstance(intents[2], RollEvent)
    assert intents[2].continuous_id == _ES
    assert desk.front_leg(_ES) == _ESU4


def test_on_bar_with_cached_roll_front_subscribes_without_requesting_instrument() -> None:
    port, native = _es_port_two_rolls()
    desk = _desk(port, present=(_ESU4,))
    desk.start(end=_dt("2024-06-06"), warmup=False)
    bar = _bar_on(native, _ESM4, date(2024, 6, 14))

    intents = desk.on_bar(bar)

    assert intents[1] == SubscribeBars(_ESU4, "1D")


def test_on_instrument_completes_a_deferred_front_leg_subscription() -> None:
    port, native = _es_port_two_rolls()
    desk = _desk(port)
    desk.start(end=_dt("2024-06-06"), warmup=False)
    desk.on_bar(_bar_on(native, _ESM4, date(2024, 6, 14)))

    intents = desk.on_instrument(_ESU4)

    assert intents == (SubscribeBars(_ESU4, "1D"),)
