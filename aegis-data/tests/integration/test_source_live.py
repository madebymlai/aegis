"""Live databento smoke test via the Nautilus port (aegis-data).

Opt-in: skipped unless ``DATABENTO_API_KEY`` is set (read from the environment
only — never committed).  Verifies the real Nautilus-port fetch, store caching,
chain assembly, snapping, and that back-adjustment yields a gap-free continuous
ES series.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from aegis_data.source import (
    continuous_panel,
    databento_contract_calendar,
    databento_leg_ports,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABENTO_API_KEY"),
    reason="DATABENTO_API_KEY not set; live databento smoke test skipped",
)


def test_live_es_continuous_panel_is_gap_free(tmp_path) -> None:
    ports = databento_leg_ports("GLBX.MDP3", store_dir=tmp_path)
    list_contracts = databento_contract_calendar("GLBX.MDP3")

    # Short window spanning one ES roll (M4 → U4) so the smoke test exercises the
    # definition-sourced expiry roll + back-adjust without a heavy multi-quarter pull.
    panel = continuous_panel(
        "ES", date(2024, 6, 1), date(2024, 9, 25),
        ports=ports, list_contracts=list_contracts, method="ratio",
        bar_cadence=timedelta(days=1),
    )

    assert not panel["Close"].isna().any()
    assert panel.index.is_monotonic_increasing
    assert list(panel.columns) == ["Open", "High", "Low", "Close", "Volume"]
    # Real ES index level (~5000s in 2024) — sanity that prices, not raw ticks, came back.
    assert panel["Close"].iloc[-1] > 1000.0
    # The store was populated with per-contract parquets.
    assert list((tmp_path / "futures-raw" / "GLBX.MDP3").glob("*/*.parquet"))
