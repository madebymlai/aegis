"""The shared home that turns a contract timeframe into the corpus' Nautilus
``BarType`` (LAST + EXTERNAL, ADR-0007) and a rebalance-period width.  An
unexpressable timeframe fails closed."""

from __future__ import annotations

import pytest
from nautilus_trader.adapters.interactive_brokers.parsing.data import what_to_show
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import (
    UnsupportedTimeframeError,
    raw_bar_type,
    timeframe_to_ns,
)

_ID = InstrumentId.from_str("AAPL.NASDAQ")


@pytest.mark.parametrize(
    ("timeframe", "step"),
    [("1D", "1-DAY"), ("15min", "15-MINUTE"), ("1H", "1-HOUR"), ("1W", "1-WEEK")],
)
def test_raw_bar_type_is_last_external_for_the_timeframe(timeframe, step):
    assert raw_bar_type(_ID, timeframe) == BarType.from_str(
        f"{_ID.value}-{step}-LAST-EXTERNAL"
    )


@pytest.mark.parametrize(
    ("instrument_id", "price_type", "what_to_show_value"),
    [
        # Cash FX serves MIDPOINT, never TRADES, on IDEALPRO (IB error 162 on a
        # TRADES request) — the FX raw daily bar is MID-EXTERNAL (ADR-0007).
        ("EUR/USD.IDEALPRO", "MID", "MIDPOINT"),
        # Everything non-FX keeps the canonical LAST-EXTERNAL identity.
        ("VWRD.LSEETF", "LAST", "TRADES"),
        ("ES.XCME", "LAST", "TRADES"),
    ],
)
def test_raw_bar_type_price_type_is_mid_for_fx_last_otherwise(
    instrument_id, price_type, what_to_show_value
):
    instrument = InstrumentId.from_str(instrument_id)
    bar_type = raw_bar_type(instrument, "1D")
    assert bar_type == BarType.from_str(
        f"{instrument_id}-1-DAY-{price_type}-EXTERNAL"
    )
    # The exact symptom: the IB ``whatToShow`` the bar type translates to.
    assert what_to_show(bar_type) == what_to_show_value


@pytest.mark.parametrize("timeframe", ["1M", "1mo", "garbage", "D", "0D"])
def test_raw_bar_type_fails_closed_on_an_unexpressable_timeframe(timeframe):
    with pytest.raises(UnsupportedTimeframeError):
        raw_bar_type(_ID, timeframe)


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
