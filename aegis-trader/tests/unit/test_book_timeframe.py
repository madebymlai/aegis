"""The Backtest Timeframe rule: all commingled sleeves must agree on one
rebalance period, or the book fails closed.  A pure book invariant over the
sleeves' declared timeframes — bar identity is single-sourced in ``aegis_data``
and tested there."""

from __future__ import annotations

import pytest

from aegis_trader.domain.book_timeframe import MixedTimeframeError, resolve_book_timeframe


def test_resolve_book_timeframe_returns_the_shared_timeframe():
    assert resolve_book_timeframe(["1D", "1D", "1D"]) == "1D"


def test_resolve_book_timeframe_fails_closed_on_mixed_timeframes():
    """All sleeves must agree — the overlay tracks one rebalance period."""
    with pytest.raises(MixedTimeframeError):
        resolve_book_timeframe(["1D", "15min"])
