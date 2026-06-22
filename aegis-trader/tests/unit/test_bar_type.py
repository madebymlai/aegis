"""Bar identity is single-sourced in ``aegis_data`` (ADR-0007); the trader
re-exports it.  What the trader *owns* is the book-cadence policy: all commingled
sleeves must agree on one rebalance period."""

from __future__ import annotations

import pytest
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.data import (
    MixedTimeframeError,
    raw_bar_type,
    resolve_book_timeframe,
)

_ID = InstrumentId.from_str("BBG000B9XRY4.SIM")


def test_raw_bar_type_re_export_is_last_external():
    """The trader's public surface re-exports the shared LAST-EXTERNAL helper."""
    assert raw_bar_type(_ID, "1D") == BarType.from_str(
        f"{_ID.value}-1-DAY-LAST-EXTERNAL"
    )


def test_resolve_book_timeframe_returns_the_shared_timeframe():
    assert resolve_book_timeframe(["1D", "1D", "1D"]) == "1D"


def test_resolve_book_timeframe_fails_closed_on_mixed_timeframes():
    """All sleeves must agree — the overlay tracks one rebalance period."""
    with pytest.raises(MixedTimeframeError):
        resolve_book_timeframe(["1D", "15min"])
