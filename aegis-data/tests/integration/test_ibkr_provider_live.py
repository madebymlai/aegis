"""Live IBKR provider check — operator-run, against a real IB Gateway.

IBKR is a true-external dependency: this test connects to a running gateway, so
it is skipped unless ``ibapi`` is installed *and* ``AEGIS_IBKR_GATEWAY_PORT`` is
set to the gateway's port.  The adapter's own logic (param translation, asyncio
hiding) is covered without IBKR in ``tests/test_ibkr_provider.py``; this only
confirms the real client actually returns ``EXTERNAL`` daily bars end to end.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import raw_bar_type
from aegis_data.ibkr_provider import IbkrHistoricalProvider

pytest.importorskip("ibapi")

_GATEWAY_PORT = os.environ.get("AEGIS_IBKR_GATEWAY_PORT")

pytestmark = pytest.mark.skipif(
    _GATEWAY_PORT is None,
    reason="set AEGIS_IBKR_GATEWAY_PORT to run against a live IB Gateway",
)


def test_request_bars_returns_external_daily_bars_from_ibkr() -> None:
    # DELAYED_FROZEN so the check runs without a real-time data subscription;
    # it validates the read path + EXTERNAL identity, not live streaming.
    provider = IbkrHistoricalProvider(
        port=int(_GATEWAY_PORT),  # type: ignore[arg-type]
        client_id=7,
        market_data_type="DELAYED_FROZEN",
    )
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    bars = provider.request_bars(
        bar_type,
        start=pd.Timestamp("2024-01-02", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
    )

    assert bars
    assert all(bar.bar_type == bar_type for bar in bars)
