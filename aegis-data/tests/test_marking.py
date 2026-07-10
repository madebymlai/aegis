"""The single raw bar-type resolution seam (aegis-rd-tggo.1).

Every raw mark/fill resolution crosses one query-only resolver returning an
``InstrumentMarking`` value object.  The prefer-LAST default adapter reproduces
today's rule byte-identically: LAST for tradeables, MID for cash FX, one mark
bar whose reference price is the bar close.
"""

from __future__ import annotations

import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.marking import (
    InstrumentMarking,
    MarkMode,
    PreferLastResolver,
    RawBarTypeResolver,
)


def _bar(bar_type: BarType, close: str) -> Bar:
    return Bar(
        bar_type=bar_type,
        open=Price.from_str(close),
        high=Price.from_str(close),
        low=Price.from_str(close),
        close=Price.from_str(close),
        volume=Quantity.from_int(1_000),
        ts_event=0,
        ts_init=0,
    )


def test_prefer_last_resolver_marks_a_tradeable_on_its_last_bar():
    marking = PreferLastResolver().resolve(InstrumentId.from_str("VWRD.LSEETF"), "1D")

    assert marking.mode is MarkMode.LAST
    assert marking.mark_bars == (BarType.from_str("VWRD.LSEETF-1-DAY-LAST-EXTERNAL"),)


def test_prefer_last_resolver_marks_cash_fx_on_its_mid_bar():
    marking = PreferLastResolver().resolve(
        InstrumentId.from_str("EUR/USD.IDEALPRO"), "1D"
    )

    assert marking.mode is MarkMode.MID
    assert marking.mark_bars == (
        BarType.from_str("EUR/USD.IDEALPRO-1-DAY-MID-EXTERNAL"),
    )


@pytest.mark.parametrize(
    ("instrument_id", "timeframe"),
    [
        ("AAPL.NASDAQ", "1D"),
        ("VWRD.LSEETF", "1W"),
        ("EUR/USD.IDEALPRO", "1D"),
        ("ES.XCME", "15min"),
    ],
)
def test_prefer_last_resolver_is_byte_identical_to_raw_bar_type(
    instrument_id, timeframe
):
    resolved = PreferLastResolver().resolve(
        InstrumentId.from_str(instrument_id), timeframe
    )

    assert resolved.mark_bars == (
        raw_bar_type(InstrumentId.from_str(instrument_id), timeframe),
    )


def test_prefer_last_resolver_canonicalizes_the_venue_like_the_corpus_key():
    marking = PreferLastResolver().resolve(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    assert marking.instrument_id == InstrumentId.from_str("AAPL.XNAS")


def test_single_bar_marking_reference_price_is_the_bar_close():
    marking = PreferLastResolver().resolve(InstrumentId.from_str("VWRD.LSEETF"), "1D")
    latest = _bar(marking.mark_bars[0], "104.25")

    assert marking.reference_price([latest]) == Price.from_str("104.25")


def test_reference_price_rejects_bars_misaligned_with_the_mark_bars():
    marking = PreferLastResolver().resolve(InstrumentId.from_str("VWRD.LSEETF"), "1D")

    with pytest.raises(ValueError):
        marking.reference_price([])


def test_prefer_last_resolver_satisfies_the_resolver_protocol():
    assert isinstance(PreferLastResolver(), RawBarTypeResolver)


def test_marking_is_an_immutable_value_object():
    marking = PreferLastResolver().resolve(InstrumentId.from_str("VWRD.LSEETF"), "1D")

    with pytest.raises(AttributeError):
        marking.mode = MarkMode.QUOTE  # type: ignore[misc]
