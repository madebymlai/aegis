"""The single raw bar-type resolution seam (aegis-rd-tggo.1/.2).

Every raw mark/fill resolution crosses one query-only resolver returning an
``InstrumentMarking`` value object.  The declared resolver reads an optional
mark-mode token stated where the instrument is named (``UEQC.IBIS:QUOTE``) plus
static instrument facts: absent token -> LAST, cash FX -> bar-marked MID, QUOTE
-> BID+ASK with a derived mid — never a stored MID bar.
"""

from __future__ import annotations

import pandas as pd
import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.marking import (
    DeclaredMarkingResolver,
    MarkDeclaration,
    MarkMode,
    RawBarTypeResolver,
    UnknownMarkTokenError,
    parse_mark_declaration,
)


def _bar(bar_type: BarType, close: str, *, day: str = "2024-01-02") -> Bar:
    ts_event = pd.Timestamp(day, tz="UTC").value
    return Bar(
        bar_type=bar_type,
        open=Price.from_str(close),
        high=Price.from_str(close),
        low=Price.from_str(close),
        close=Price.from_str(close),
        volume=Quantity.from_int(1_000),
        ts_event=ts_event,
        ts_init=ts_event,
    )


# ── the declaration token (parsed once at config load) ─────────────────────


def test_parse_mark_declaration_reads_the_quote_token():
    declaration = parse_mark_declaration("UEQC.IBIS:QUOTE")

    assert declaration == MarkDeclaration(
        instrument_id=InstrumentId.from_str("UEQC.IBIS"), mode=MarkMode.QUOTE
    )


def test_parse_mark_declaration_reads_the_mid_token():
    declaration = parse_mark_declaration("EUR/USD.IDEALPRO:MID")

    assert declaration == MarkDeclaration(
        instrument_id=InstrumentId.from_str("EUR/USD.IDEALPRO"), mode=MarkMode.MID
    )


def test_parse_mark_declaration_without_a_token_declares_no_mode():
    declaration = parse_mark_declaration("VWRD.LSEETF")

    assert declaration == MarkDeclaration(
        instrument_id=InstrumentId.from_str("VWRD.LSEETF"), mode=None
    )


@pytest.mark.parametrize("value", ["UEQC.IBIS:FOO", "UEQC.IBIS:quote", "UEQC.IBIS:"])
def test_parse_mark_declaration_fails_closed_on_an_unknown_token(value):
    with pytest.raises(UnknownMarkTokenError):
        parse_mark_declaration(value)


# ── the resolver: declaration + static facts -> InstrumentMarking ──────────


def test_undeclared_tradeable_resolves_to_its_last_bar():
    marking = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str("VWRD.LSEETF"), "1D"
    )

    assert marking.mode is MarkMode.LAST
    assert marking.mark_bars == (BarType.from_str("VWRD.LSEETF-1-DAY-LAST-EXTERNAL"),)


def test_a_declared_cash_fx_conversion_leg_resolves_to_its_mid_bar():
    # The config layer supplies this declaration structurally: an ``exchange:``
    # conversion leg is MID because the section that names it says what it is.
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("EUR/USD.IDEALPRO"): MarkMode.MID}
    )

    marking = resolver.resolve(InstrumentId.from_str("EUR/USD.IDEALPRO"), "1D")

    assert marking.mode is MarkMode.MID
    assert marking.mark_bars == (
        BarType.from_str("EUR/USD.IDEALPRO-1-DAY-MID-EXTERNAL"),
    )


def test_an_undeclared_cash_fx_id_resolves_last_like_anything_else():
    # No shape heuristic: undeclared means LAST, FX included. A tradeable FX
    # pair therefore needs an explicit :MID, and a forgotten one fails loud at
    # the gateway (IB error 162) instead of silently guessing.
    marking = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str("EUR/USD.IDEALPRO"), "1D"
    )

    assert marking.mode is MarkMode.LAST


def test_declared_quote_resolves_to_bid_and_ask_external_bars():
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    )

    marking = resolver.resolve(InstrumentId.from_str("UEQC.IBIS"), "1D")

    assert marking.mode is MarkMode.QUOTE
    assert marking.mark_bars == (
        BarType.from_str("UEQC.XETR-1-DAY-BID-EXTERNAL"),
        BarType.from_str("UEQC.XETR-1-DAY-ASK-EXTERNAL"),
    )


def test_a_quote_marking_never_carries_a_mid_external_bar():
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    )

    marking = resolver.resolve(InstrumentId.from_str("UEQC.IBIS"), "1D")

    assert all("MID" not in str(bar_type) for bar_type in marking.mark_bars)


def test_declared_mid_resolves_to_the_single_mid_bar():
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("XEON.IBIS"): MarkMode.MID}
    )

    marking = resolver.resolve(InstrumentId.from_str("XEON.IBIS"), "1D")

    assert marking.mode is MarkMode.MID
    assert marking.mark_bars == (BarType.from_str("XEON.XETR-1-DAY-MID-EXTERNAL"),)


def test_a_declaration_resolves_under_the_canonical_venue_spelling():
    # Declared under the raw IB exchange, resolved by the MIC id (or vice versa):
    # both spellings are one instrument in the Catalog.
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    )

    marking = resolver.resolve(InstrumentId.from_str("UEQC.XETR"), "1D")

    assert marking.mode is MarkMode.QUOTE


@pytest.mark.parametrize(
    ("instrument_id", "timeframe"),
    [
        # FX included: raw_bar_type and the resolver share one undeclared
        # default (LAST) — nothing anywhere derives a price type from the id.
        ("AAPL.NASDAQ", "1D"),
        ("VWRD.LSEETF", "1W"),
        ("EUR/USD.IDEALPRO", "1D"),
        ("ES.XCME", "15min"),
    ],
)
def test_undeclared_resolution_is_byte_identical_to_raw_bar_type(
    instrument_id, timeframe
):
    resolved = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str(instrument_id), timeframe
    )

    assert resolved.mark_bars == (
        raw_bar_type(InstrumentId.from_str(instrument_id), timeframe),
    )


def test_resolution_canonicalizes_the_venue_like_the_catalog_key():
    marking = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str("AAPL.NASDAQ"), "1D"
    )

    assert marking.instrument_id == InstrumentId.from_str("AAPL.XNAS")


def test_the_declared_resolver_satisfies_the_resolver_protocol():
    assert isinstance(DeclaredMarkingResolver(), RawBarTypeResolver)


# ── the marking value object: reference price + frame projection ───────────


def test_single_bar_marking_reference_price_is_the_bar_close():
    marking = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str("VWRD.LSEETF"), "1D"
    )
    latest = _bar(marking.mark_bars[0], "104.25")

    assert marking.reference_price([latest]) == Price.from_str("104.25")


def test_quote_marking_reference_price_is_the_bid_ask_mid():
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    )
    marking = resolver.resolve(InstrumentId.from_str("UEQC.IBIS"), "1D")
    bid = _bar(marking.mark_bars[0], "100.00")
    ask = _bar(marking.mark_bars[1], "100.50")

    assert marking.reference_price([bid, ask]).as_double() == pytest.approx(100.25)


def test_reference_price_rejects_bars_misaligned_with_the_mark_bars():
    from aegis_data.marking import MarkBarMisalignmentError

    marking = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str("VWRD.LSEETF"), "1D"
    )

    with pytest.raises(MarkBarMisalignmentError):
        marking.reference_price([])


def test_bar_marked_ohlcv_frame_is_the_bars_own_ohlcv():
    marking = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str("VWRD.LSEETF"), "1D"
    )
    bars = [_bar(marking.mark_bars[0], "104.25")]

    frame = marking.ohlcv_frame({marking.mark_bars[0]: bars})

    assert frame["Close"].tolist() == [104.25]


def test_quote_marked_ohlcv_frame_is_the_derived_mid_of_bid_and_ask():
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    )
    marking = resolver.resolve(InstrumentId.from_str("UEQC.IBIS"), "1D")
    bid_bars = [
        _bar(marking.mark_bars[0], "100.00", day="2024-01-02"),
        _bar(marking.mark_bars[0], "102.00", day="2024-01-03"),
    ]
    ask_bars = [
        _bar(marking.mark_bars[1], "100.50", day="2024-01-02"),
        _bar(marking.mark_bars[1], "102.50", day="2024-01-03"),
    ]

    frame = marking.ohlcv_frame(
        {marking.mark_bars[0]: bid_bars, marking.mark_bars[1]: ask_bars}
    )

    assert frame["Close"].tolist() == [100.25, 102.25]


def test_quote_marked_ohlcv_frame_keeps_only_days_quoted_on_both_sides():
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    )
    marking = resolver.resolve(InstrumentId.from_str("UEQC.IBIS"), "1D")
    bid_bars = [
        _bar(marking.mark_bars[0], "100.00", day="2024-01-02"),
        _bar(marking.mark_bars[0], "102.00", day="2024-01-03"),
    ]
    ask_bars = [_bar(marking.mark_bars[1], "100.50", day="2024-01-02")]

    frame = marking.ohlcv_frame(
        {marking.mark_bars[0]: bid_bars, marking.mark_bars[1]: ask_bars}
    )

    assert frame.index.tolist() == [pd.Timestamp("2024-01-02")]


def test_quote_marking_exposes_its_sided_bid_and_ask_frames():
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    )
    marking = resolver.resolve(InstrumentId.from_str("UEQC.IBIS"), "1D")
    bid_bars = [_bar(marking.mark_bars[0], "100.00")]
    ask_bars = [_bar(marking.mark_bars[1], "100.50")]

    sided = marking.quote_ohlcv_frames(
        {marking.mark_bars[0]: bid_bars, marking.mark_bars[1]: ask_bars}
    )

    assert sided is not None
    bid_frame, ask_frame = sided
    assert bid_frame["Close"].tolist() == [100.0]
    assert ask_frame["Close"].tolist() == [100.5]


def test_bar_marked_instrument_has_no_sided_quote_frames():
    marking = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str("VWRD.LSEETF"), "1D"
    )
    bars = [_bar(marking.mark_bars[0], "104.25")]

    assert marking.quote_ohlcv_frames({marking.mark_bars[0]: bars}) is None


def test_quote_marking_derived_mark_is_the_mid_of_a_complete_pair():
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    )
    marking = resolver.resolve(InstrumentId.from_str("UEQC.IBIS"), "1D")
    bid = _bar(marking.mark_bars[0], "100.00")
    ask = _bar(marking.mark_bars[1], "100.50")

    mark = marking.derived_mark({marking.mark_bars[0]: bid, marking.mark_bars[1]: ask})

    assert mark is not None
    assert mark.as_double() == pytest.approx(100.25)


def test_quote_marking_derived_mark_waits_for_a_same_timestamp_pair():
    resolver = DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    )
    marking = resolver.resolve(InstrumentId.from_str("UEQC.IBIS"), "1D")
    bid = _bar(marking.mark_bars[0], "100.00", day="2024-01-02")
    stale_ask = _bar(marking.mark_bars[1], "100.50", day="2024-01-01")

    mark = marking.derived_mark(
        {marking.mark_bars[0]: bid, marking.mark_bars[1]: stale_ask}
    )

    assert mark is None


def test_bar_marked_instrument_publishes_no_derived_mark():
    marking = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str("VWRD.LSEETF"), "1D"
    )
    latest = _bar(marking.mark_bars[0], "104.25")

    assert marking.derived_mark({marking.mark_bars[0]: latest}) is None


def test_marking_for_mode_is_the_one_builder_shared_by_resolvers():
    from aegis_data.marking import marking_for_mode

    marking = marking_for_mode(InstrumentId.from_str("UEQC.IBIS"), "1D", MarkMode.QUOTE)

    assert marking == DeclaredMarkingResolver(
        declared={InstrumentId.from_str("UEQC.IBIS"): MarkMode.QUOTE}
    ).resolve(InstrumentId.from_str("UEQC.IBIS"), "1D")


def test_marking_is_an_immutable_value_object():
    marking = DeclaredMarkingResolver().resolve(
        InstrumentId.from_str("VWRD.LSEETF"), "1D"
    )

    with pytest.raises(AttributeError):
        marking.mode = MarkMode.QUOTE  # type: ignore[misc]
