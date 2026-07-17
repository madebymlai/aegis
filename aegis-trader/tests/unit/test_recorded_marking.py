"""Live-side recorded markings (aegis-rd-tggo.3).

Live resolution is a read-only view over the bundle-recorded mark modes: it
subscribes exactly the mark research validated, fails closed on an unrecorded
id, and reserves the LAST fallback for continuous-future legs (LAST by
construction).  Verified at the recorded-marking seam — no broker.
"""

from __future__ import annotations

import pytest
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.marking import MarkMode
from aegis_trader.bundles.marking import (
    ConflictingRecordedMarkingsError,
    MissingRecordedMarkingError,
    RecordedMarkingResolver,
)


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def test_a_recorded_quote_leg_resolves_to_bid_and_ask_subscriptions():
    resolver = RecordedMarkingResolver(recorded={_id("UEQC.XETR"): MarkMode.QUOTE})

    marking = resolver.resolve(_id("UEQC.XETR"), "1D")

    assert marking.mark_bars == (
        BarType.from_str("UEQC.XETR-1-DAY-BID-EXTERNAL"),
        BarType.from_str("UEQC.XETR-1-DAY-ASK-EXTERNAL"),
    )


def test_a_recorded_bar_marked_leg_resolves_to_its_single_feed():
    resolver = RecordedMarkingResolver(recorded={_id("VUSA.XLON"): MarkMode.LAST})

    marking = resolver.resolve(_id("VUSA.XLON"), "1D")

    assert marking.mark_bars == (BarType.from_str("VUSA.XLON-1-DAY-LAST-EXTERNAL"),)


def test_a_recorded_cash_fx_leg_resolves_bar_marked_mid_not_trades():
    # Regression guard: live FX must never flip to a TRADES/LAST feed.
    resolver = RecordedMarkingResolver(
        recorded={_id("EUR/USD.IDEALPRO"): MarkMode.MID}
    )

    marking = resolver.resolve(_id("EUR/USD.IDEALPRO"), "1D")

    assert marking.mark_bars == (
        BarType.from_str("EUR/USD.IDEALPRO-1-DAY-MID-EXTERNAL"),
    )


def test_an_unrecorded_id_fails_closed_with_a_clear_error():
    resolver = RecordedMarkingResolver(recorded={_id("VUSA.XLON"): MarkMode.LAST})

    with pytest.raises(MissingRecordedMarkingError, match="UEQC.XETR"):
        resolver.resolve(_id("UEQC.XETR"), "1D")


def test_a_declared_roots_dated_leg_falls_back_to_last_by_construction():
    resolver = RecordedMarkingResolver(recorded={}, futures_roots=frozenset({"ES"}))

    marking = resolver.resolve(_id("ESM4.XCME"), "1D")

    assert marking.mode is MarkMode.LAST


def test_a_declared_roots_synthetic_continuous_id_is_last_by_construction():
    resolver = RecordedMarkingResolver(recorded={}, futures_roots=frozenset({"ES"}))

    marking = resolver.resolve(_id("ES.XCME"), "1D")

    assert marking.mode is MarkMode.LAST


def test_a_non_leg_symbol_sharing_a_root_prefix_still_fails_closed():
    resolver = RecordedMarkingResolver(recorded={}, futures_roots=frozenset({"ES"}))

    with pytest.raises(MissingRecordedMarkingError):
        resolver.resolve(_id("ESTX50.XEUR"), "1D")


def test_a_recording_resolves_under_the_canonical_venue_spelling():
    resolver = RecordedMarkingResolver(recorded={_id("UEQC.IBIS"): MarkMode.QUOTE})

    marking = resolver.resolve(_id("UEQC.XETR"), "1D")

    assert marking.mode is MarkMode.QUOTE


def test_the_live_view_is_read_only_with_no_record_surface():
    resolver = RecordedMarkingResolver(recorded={_id("VUSA.XLON"): MarkMode.LAST})

    callables = sorted(
        name
        for name in dir(resolver)
        if not name.startswith("_") and callable(getattr(resolver, name))
    )

    # The whole verb surface is the one query — no resolve-and-record, no fill.
    assert callables == ["resolve"]


def test_conflicting_recordings_across_sleeves_fail_loud():
    from aegis_trader.bundles.marking import union_recorded_markings

    with pytest.raises(ConflictingRecordedMarkingsError, match="UEQC.XETR"):
        union_recorded_markings(
            [
                {_id("UEQC.XETR"): "QUOTE"},
                {_id("UEQC.IBIS"): "LAST"},
            ]
        )
