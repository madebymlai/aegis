"""Nautilus databento port fetcher (aegis-data).

The port path (definitions → bars → pandas) is verified with a fake async
client; the live call is covered by the env-gated smoke test.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from aegis_data.databento_port import bars_to_ohlcv, databento_port_fetcher


class _Px:
    def __init__(self, value: float) -> None:
        self._value = value

    def as_double(self) -> float:
        return self._value


class _Bar:
    def __init__(self, ts: int, o: float, h: float, low: float, c: float, v: float) -> None:
        self.ts_event = ts
        self.open, self.high, self.low, self.close, self.volume = (
            _Px(o), _Px(h), _Px(low), _Px(c), _Px(v),
        )


class _FakeClient:
    def __init__(self, bars: list[_Bar]) -> None:
        self._bars = bars
        self.calls: list[str] = []

    async def get_range_instruments(self, *args, **kwargs) -> list:
        self.calls.append("instruments")
        return []

    async def get_range_bars(self, *args, **kwargs) -> list[_Bar]:
        self.calls.append("bars")
        return self._bars


def test_bars_to_ohlcv_normalizes_pyo3_bars() -> None:
    bars = [_Bar(pd.Timestamp("2024-09-13").value, 5665.75, 5702.25, 5659.75, 5687.5, 291354)]

    df = bars_to_ohlcv(bars)

    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.index.tz is None
    assert df.loc[pd.Timestamp("2024-09-13"), "Close"] == 5687.5
    assert df.loc[pd.Timestamp("2024-09-13"), "Volume"] == 291354.0


def test_fetcher_loads_definitions_before_bars() -> None:
    client = _FakeClient([_Bar(pd.Timestamp("2024-09-13").value, 1.0, 2.0, 0.5, 1.5, 100)])
    fetch = databento_port_fetcher("GLBX.MDP3", client=client)

    df = fetch("ESZ4", date(2024, 9, 13), date(2024, 9, 13))

    # Definitions must be fetched before bars (so the port resolves precision).
    assert client.calls == ["instruments", "bars"]
    assert df.loc[pd.Timestamp("2024-09-13"), "Close"] == 1.5
