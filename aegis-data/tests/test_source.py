"""End-to-end offline composition (aegis-data): port → store cache → chain → back-adjust.

Uses a fake pyo3-style client so the whole `continuous_panel` path is exercised
without network — the real databento call is covered by the live smoke test.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from aegis_data.roll import DatedContract
from aegis_data.source import continuous_panel, databento_source

_BASIS = {"ESH4": 100.0, "ESM4": 200.0, "ESU4": 300.0, "ESZ4": 400.0}


def _es_2024(root: str, start: date, end: date) -> list[DatedContract]:
    return [
        DatedContract("ESH4", date(2024, 3, 15)),
        DatedContract("ESM4", date(2024, 6, 21)),
        DatedContract("ESU4", date(2024, 9, 20)),
        DatedContract("ESZ4", date(2024, 12, 20)),
    ]


class _Px:
    def __init__(self, v: float) -> None:
        self._v = v

    def as_double(self) -> float:
        return self._v


class _Bar:
    def __init__(self, ts: int, c: float) -> None:
        self.ts_event = ts
        self.open = self.high = self.low = self.close = _Px(c)
        self.volume = _Px(1.0)


class _FakeClient:
    """Generates per-contract daily bars from the requested instrument + window."""

    def __init__(self) -> None:
        self.bar_calls = 0

    async def get_range_instruments(self, *args, **kwargs) -> list:
        return []

    async def get_range_bars(self, dataset, instrument_ids, aggregation, start_ns, end_ns, **kwargs):
        self.bar_calls += 1
        symbol = instrument_ids[0].symbol.value
        base = _BASIS[symbol]
        idx = pd.bdate_range(pd.Timestamp(start_ns), pd.Timestamp(end_ns))
        return [_Bar(ts.value, base + i) for i, ts in enumerate(idx)]


def test_continuous_panel_back_adjusts_and_caches(tmp_path) -> None:
    client = _FakeClient()
    fetch = databento_source("GLBX.MDP3", store_dir=tmp_path, client=client)

    panel = continuous_panel(
        "ES", date(2024, 1, 1), date(2024, 12, 31),
        fetch=fetch, list_contracts=_es_2024, method="ratio",
        bar_cadence=timedelta(days=1),
    )

    # Gap-free continuous panel covering the year; most-recent contract (ESZ4) unadjusted.
    assert not panel["Close"].isna().any()
    assert panel.index.is_monotonic_increasing
    assert list(panel.columns) == ["Open", "High", "Low", "Close", "Volume"]
    calls_after_first = client.bar_calls
    assert calls_after_first == 4  # one per contract

    # A second resolution reads the store — no further provider hits.
    again = continuous_panel(
        "ES", date(2024, 1, 1), date(2024, 12, 31),
        fetch=fetch, list_contracts=_es_2024, method="ratio",
        bar_cadence=timedelta(days=1),
    )
    assert client.bar_calls == calls_after_first
    pd.testing.assert_frame_equal(panel, again)
