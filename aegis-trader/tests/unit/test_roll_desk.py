"""Roll Desk unit tests: continuous-roll state in, typed intents out."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.domain.roll import (
    Halt,
    RequestBars,
    RequestInstrument,
    RollEvent,
    SubscribeBars,
    UnsubscribeBars,
)
from aegis_trader.bundles.book_sleeves import ContinuousRootDeclaration
from aegis_trader.domain.startup import StartupGate
from aegis_trader.trader.roll_desk import RollDesk

from aegis_data.testing import es_port, es_port_two_rolls

_HISTORY_START = datetime(2024, 1, 15, tzinfo=timezone.utc)
_ES = InstrumentId.from_str("ES.XCME")
_ES_IFUS = InstrumentId.from_str("ES.IFUS")
_ESH4 = InstrumentId.from_str("ESH4.XCME")
_ESM4 = InstrumentId.from_str("ESM4.XCME")
_ESU4 = InstrumentId.from_str("ESU4.XCME")


def _desk(port, *, present: tuple[InstrumentId, ...] = ()) -> RollDesk:
    present_set = set(present)
    return RollDesk(
        catalog_port=port,
        instrument_present=present_set.__contains__,
    )


def _declarations(
    *,
    declared: InstrumentId = _ES,
    adjustment_mode: ContinuousFutureAdjustmentType = (
        ContinuousFutureAdjustmentType.BACKWARD_RATIO
    ),
) -> dict[str, ContinuousRootDeclaration]:
    return {
        "ES": ContinuousRootDeclaration(
            continuous_id=declared, adjustment_mode=adjustment_mode
        )
    }


def _dt(day: str) -> datetime:
    return datetime.combine(pd.Timestamp(day).date(), datetime.min.time(), timezone.utc)


def _bar_on(native: dict[InstrumentId, list[Bar]], instrument_id: InstrumentId, day: date) -> Bar:
    return next(
        bar
        for bar in native[instrument_id]
        if pd.Timestamp(bar.ts_event, tz="UTC").date() == day
    )


def test_start_returns_front_leg_warmup_and_subscribe_intents() -> None:
    port, _native = es_port()
    desk = _desk(port)

    intents = desk.start(
        timeframe="1D",
        history_start=_HISTORY_START,
        end=_dt("2024-02-15"),
        warmup=True,
        declarations=_declarations(),
    )

    assert intents == (
        RequestBars(_ESH4, "1D", _HISTORY_START, _dt("2024-02-15")),
        SubscribeBars(_ESH4, "1D"),
    )
    assert desk.front_leg(_ES) == _ESH4
    assert desk.series(_ES) is not None


def test_start_materializes_under_the_declarations_mode() -> None:
    """The declaration's mode drives materialisation, so the same root produces
    different adjusted histories under ratio vs spread — and a spread roll later
    emits an additive Rebasing automatically (the model owns the algebra)."""
    port, _ = es_port()
    ratio_desk = _desk(port)
    ratio_desk.start(
        timeframe="1D",
        history_start=_HISTORY_START,
        end=_dt("2024-04-30"),
        warmup=False,
        declarations=_declarations(),
    )
    spread_desk = _desk(port)
    spread_desk.start(
        timeframe="1D",
        history_start=_HISTORY_START,
        end=_dt("2024-04-30"),
        warmup=False,
        declarations=_declarations(
            adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD
        ),
    )

    ratio_series = ratio_desk.series(_ES)
    spread_series = spread_desk.series(_ES)
    assert ratio_series is not None and spread_series is not None
    # The window spans the ESH4->ESM4 roll, so the two algebras produce different
    # back-adjusted histories from the same legs.
    assert ratio_series["Close"].tolist() != spread_series["Close"].tolist()


def test_roll_emits_multiplicative_rebasing_under_ratio_and_additive_under_spread() -> None:
    port, native = es_port_two_rolls()
    results: dict[str, float] = {}
    for label, mode in (
        ("ratio", ContinuousFutureAdjustmentType.BACKWARD_RATIO),
        ("spread", ContinuousFutureAdjustmentType.BACKWARD_SPREAD),
    ):
        desk = _desk(port)
        desk.start(
            timeframe="1D",
            history_start=_HISTORY_START,
            end=_dt("2024-06-06"),
            warmup=False,
            declarations=_declarations(adjustment_mode=mode),
        )
        intents = desk.on_bar(_bar_on(native, _ESM4, date(2024, 6, 14)))
        event = next(intent for intent in intents if isinstance(intent, RollEvent))
        results[label] = event.rebasing.apply(0.0)

    # Applying to 0 isolates the additive part: multiplicative carry maps 0 -> 0,
    # additive carry maps 0 -> its offset.
    assert results["ratio"] == pytest.approx(0.0)
    assert results["spread"] != pytest.approx(0.0)


def test_start_halts_when_materialized_continuous_venue_differs_from_declaration() -> None:
    port, _native = es_port()
    desk = _desk(port)

    intents = desk.start(
        timeframe="1D",
        history_start=_HISTORY_START,
        end=_dt("2024-02-15"),
        warmup=True,
        declarations=_declarations(declared=_ES_IFUS),
    )

    assert intents == (
        Halt(
            StartupGate.CONTINUOUS_IDENTITY,
            "continuous root 'ES' materialized as ES.XCME, expected ES.IFUS",
        ),
    )


def test_on_bar_without_a_roll_appends_offset_zero_and_emits_no_intents() -> None:
    port, native = es_port_two_rolls()
    desk = _desk(port)
    desk.start(
        timeframe="1D",
        history_start=_HISTORY_START,
        end=_dt("2024-05-10"),
        warmup=False,
        declarations=_declarations(),
    )
    series_before = desk.series(_ES)
    bar = _bar_on(native, _ESM4, date(2024, 5, 13))

    intents = desk.on_bar(bar)

    series_after = desk.series(_ES)
    assert series_before is not None
    assert series_after is not None
    assert intents == ()
    assert len(series_after) == len(series_before) + 1


def test_on_bar_with_a_roll_returns_unsubscribe_ensure_new_and_roll_event() -> None:
    port, native = es_port_two_rolls()
    desk = _desk(port)
    desk.start(
        timeframe="1D",
        history_start=_HISTORY_START,
        end=_dt("2024-06-06"),
        warmup=False,
        declarations=_declarations(),
    )
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
    port, native = es_port_two_rolls()
    desk = _desk(port, present=(_ESU4,))
    desk.start(
        timeframe="1D",
        history_start=_HISTORY_START,
        end=_dt("2024-06-06"),
        warmup=False,
        declarations=_declarations(),
    )
    bar = _bar_on(native, _ESM4, date(2024, 6, 14))

    intents = desk.on_bar(bar)

    assert intents[1] == SubscribeBars(_ESU4, "1D")


def test_on_instrument_completes_a_deferred_front_leg_subscription() -> None:
    port, native = es_port_two_rolls()
    desk = _desk(port)
    desk.start(
        timeframe="1D",
        history_start=_HISTORY_START,
        end=_dt("2024-06-06"),
        warmup=False,
        declarations=_declarations(),
    )
    desk.on_bar(_bar_on(native, _ESM4, date(2024, 6, 14)))

    intents = desk.on_instrument(_ESU4)

    assert intents == (SubscribeBars(_ESU4, "1D"),)
