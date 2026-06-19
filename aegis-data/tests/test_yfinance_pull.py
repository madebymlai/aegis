"""YFinance listed-instrument Pulls (aegis-data)."""

from __future__ import annotations

import pandas as pd
import pytest
from aegis_runtime import FuturesRef, ListedRef

from aegis_data.store import NativeBarsRequest, read_native_bars
from aegis_data.yfinance import YFinanceLocator, pull_yfinance_native_bars


def _bars(base: float) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-02", periods=3)
    return pd.DataFrame(
        {
            "Open": [base, base + 1.0, base + 2.0],
            "High": [base, base + 1.0, base + 2.0],
            "Low": [base, base + 1.0, base + 2.0],
            "Close": [base, base + 1.0, base + 2.0],
            "Volume": [1000, 1100, 1200],
        },
        index=index,
    )


def test_yfinance_pull_writes_native_bars_under_listed_ref_not_locator(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    calls: list[str] = []

    def fetch(locator: YFinanceLocator, request: NativeBarsRequest) -> pd.DataFrame:
        calls.append(locator.ticker)
        return _bars(100.0 if locator.ticker == "BRK-B" else 200.0)

    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Open", "High", "Low", "Close", "Volume"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
    )

    pull_yfinance_native_bars(
        request, YFinanceLocator("BRK-B"), fetcher=fetch, store_dir=tmp_path
    )
    pull_yfinance_native_bars(
        request, YFinanceLocator("BRK.B"), fetcher=fetch, store_dir=tmp_path
    )

    frames = read_native_bars(
        (ref,),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        store_dir=tmp_path,
    )

    assert calls == ["BRK-B", "BRK.B"]
    assert frames[ref]["Close"].tolist() == [200.0, 201.0, 202.0]
    assert sorted(path.name for path in (tmp_path / "listed").iterdir()) == ["BBG000B9XRY4"]


def test_yfinance_pull_requires_one_explicit_listed_ref(tmp_path) -> None:
    request = NativeBarsRequest(
        refs=(FuturesRef("ES", "GLBX.MDP3"),),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
    )

    with pytest.raises(TypeError, match="ListedRef"):
        pull_yfinance_native_bars(
            request,
            YFinanceLocator("ES=F"),
            fetcher=lambda _locator, _request: _bars(100.0),
            store_dir=tmp_path,
        )
