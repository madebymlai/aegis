"""The single source of truth that turns a DataContract timeframe into the
Nautilus bar type the overlay loads and subscribes (LAST + EXTERNAL), and into
the rebalance period width.  An unexpressable timeframe fails closed."""

from __future__ import annotations

import pytest
from nautilus_trader.model.data import BarType

from aegis_trader.data.bar_type import (
    MixedTimeframeError,
    UnsupportedTimeframeError,
    bar_type,
    resolve_book_timeframe,
    timeframe_to_ns,
)

_IID = "BBG000B9XRY4.SIM"


@pytest.mark.parametrize(
    ("timeframe", "step"),
    [("1D", "1-DAY"), ("15min", "15-MINUTE"), ("1H", "1-HOUR")],
)
def test_bar_type_maps_contract_timeframe_to_a_nautilus_bar_type(timeframe, step):
    assert bar_type(_IID, timeframe) == BarType.from_str(f"{_IID}-{step}-LAST-EXTERNAL")


@pytest.mark.parametrize("timeframe", ["1M", "1mo", "garbage", "D", "0D"])
def test_bar_type_fails_closed_on_an_unexpressable_timeframe(timeframe):
    with pytest.raises(UnsupportedTimeframeError):
        bar_type(_IID, timeframe)


@pytest.mark.parametrize(
    ("timeframe", "ns"),
    [
        ("1D", 86_400_000_000_000),
        ("15min", 900_000_000_000),
        ("1H", 3_600_000_000_000),
    ],
)
def test_timeframe_to_ns_gives_the_rebalance_period_width(timeframe, ns):
    assert timeframe_to_ns(timeframe) == ns


def test_resolve_book_timeframe_returns_the_shared_timeframe():
    assert resolve_book_timeframe(["1D", "1D", "1D"]) == "1D"


def test_resolve_book_timeframe_fails_closed_on_mixed_timeframes():
    """All sleeves must agree — the overlay tracks one rebalance period."""
    with pytest.raises(MixedTimeframeError):
        resolve_book_timeframe(["1D", "15min"])
