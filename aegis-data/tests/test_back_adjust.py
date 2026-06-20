"""Panel back-adjustment for a futures chain (aegis-data).

``back_adjust_chain`` turns a ``ContractChain`` into one continuous OHLCV panel:
Open/High/Low/Close are adjusted by the SAME Close-derived roll factors, and
Volume is stitched without adjustment.
"""

from __future__ import annotations

import pandas as pd
import pytest

from aegis_data.back_adjust import back_adjust_chain
from aegis_data.chain import ContractChain


def _frame(dates: list[str], close: list[float], opens: list[float], vol: list[int]) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame(
        {"Open": opens, "High": [c + 1 for c in close], "Low": [c - 1 for c in close],
         "Close": close, "Volume": vol},
        index=idx,
    )


def test_back_adjust_chain_applies_close_factors_to_ohlc_and_passes_volume() -> None:
    a = _frame(["2024-01-01", "2024-01-02", "2024-01-03"], [100.0, 101.0, 102.0],
               opens=[100.5, 101.5, 103.0], vol=[10, 11, 12])
    b = _frame(["2024-01-02", "2024-01-03", "2024-01-04"], [121.0, 122.0, 123.0],
               opens=[121.5, 124.0, 123.5], vol=[20, 21, 22])
    roll = pd.Timestamp("2024-01-03")
    chain = ContractChain(symbols=("ESH4", "ESM4"), roll_dates=(roll,), frames=(a, b))

    panel = back_adjust_chain(chain, method="ratio")

    close_factor = 122.0 / 102.0
    assert panel["Close"].loc[roll] == 122.0
    assert panel["Open"].loc[roll] == 124.0
    assert panel["Open"].loc["2024-01-01"] == pytest.approx(100.5 * close_factor)
    assert panel["Close"].loc["2024-01-01"] == pytest.approx(100.0 * close_factor)
    assert panel["Volume"].loc["2024-01-01"] == 10
    assert panel["Volume"].loc[roll] == 21
    assert list(panel.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert panel.index.is_monotonic_increasing
