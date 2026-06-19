"""Ensure Coverage Pull dispatch (aegis-data).

These tests pin the asset-class dispatch matrix that used to live in the RD store
adapter: which Pull runs for each ``(InstrumentRef, GapFillProvider)`` pair, and
how Provider Locators flow to the providers that need them.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from aegis_runtime import FuturesRef, ListedRef

from aegis_data.calendars import TradingCalendar
from aegis_data.coverage import GapFillProvider, ensure_native_bar_coverage
from aegis_data.store import NativeBarsRequest, read_native_bars
from aegis_data.yfinance import FetchWindow, YFinanceLocator

_ARRAYS = ("Open", "High", "Low", "Close", "Volume")


def _request(*refs: object) -> NativeBarsRequest:
    return NativeBarsRequest(
        refs=refs,
        arrays=_ARRAYS,
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
    )


def _bars() -> pd.DataFrame:
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])
    return pd.DataFrame(
        {
            "Open": [10.0, 11.0, 12.0],
            "High": [10.0, 11.0, 12.0],
            "Low": [10.0, 11.0, 12.0],
            "Close": [10.0, 11.0, 12.0],
            "Volume": [1000, 1100, 1200],
        },
        index=index,
    )


def test_ensure_coverage_dispatches_listed_ref_to_yfinance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ref = ListedRef("BBG000B9XRY4")
    tickers: list[str] = []

    def fetch(locator: YFinanceLocator, _window: FetchWindow) -> pd.DataFrame:
        tickers.append(locator.ticker)
        return _bars()

    monkeypatch.setattr("aegis_data.yfinance._fetch_yfinance", fetch)

    ensure_native_bar_coverage(
        _request(ref),
        provider=GapFillProvider.YFINANCE,
        locators={ref: "BRK-B"},
        store_dir=tmp_path,
    )

    frames = read_native_bars(
        (ref,),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
        store_dir=tmp_path,
    )
    assert tickers == ["BRK-B"]
    assert frames[ref]["Close"].tolist() == [10.0, 11.0, 12.0]


def test_ensure_coverage_pulls_each_listed_ref_with_its_own_locator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = ListedRef("BBG000B9XRY4")
    second = ListedRef("BBG000BPH459")
    tickers: list[str] = []

    def fetch(locator: YFinanceLocator, _window: FetchWindow) -> pd.DataFrame:
        tickers.append(locator.ticker)
        return _bars()

    monkeypatch.setattr("aegis_data.yfinance._fetch_yfinance", fetch)

    ensure_native_bar_coverage(
        _request(first, second),
        provider=GapFillProvider.YFINANCE,
        locators={first: "BRK-B", second: "MSFT"},
        store_dir=tmp_path,
    )

    assert tickers == ["BRK-B", "MSFT"]


def test_ensure_coverage_dispatches_futures_ref_to_databento(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ref = FuturesRef("ES", "GLBX.MDP3", "calendar", "unadjusted")
    seen: list[tuple[NativeBarsRequest, object]] = []

    def pull(request: NativeBarsRequest, *, store_dir: object = None, **_kwargs: object) -> object:
        seen.append((request, store_dir))
        return object()

    monkeypatch.setattr("aegis_data.coverage.pull_databento_futures_bars", pull)

    ensure_native_bar_coverage(
        _request(ref),
        provider=GapFillProvider.DATABENTO,
        locators={ref: "ES"},
        store_dir=tmp_path,
    )

    assert len(seen) == 1
    forwarded, store_dir = seen[0]
    assert forwarded.refs == (ref,)
    assert store_dir == tmp_path


def test_ensure_coverage_requires_locator_for_yfinance(tmp_path: Path) -> None:
    ref = ListedRef("BBG000B9XRY4")

    with pytest.raises(ValueError, match="provider locator"):
        ensure_native_bar_coverage(
            _request(ref),
            provider=GapFillProvider.YFINANCE,
            locators={},
            store_dir=tmp_path,
        )


def test_ensure_coverage_rejects_listed_ref_with_futures_provider(tmp_path: Path) -> None:
    ref = ListedRef("BBG000B9XRY4")

    with pytest.raises(ValueError, match="unsupported store gap-fill provider"):
        ensure_native_bar_coverage(
            _request(ref),
            provider=GapFillProvider.DATABENTO,
            locators={ref: "BRK-B"},
            store_dir=tmp_path,
        )


def test_ensure_coverage_rejects_futures_ref_with_listed_provider(tmp_path: Path) -> None:
    ref = FuturesRef("ES", "GLBX.MDP3", "calendar", "unadjusted")

    with pytest.raises(ValueError, match="unsupported store gap-fill provider"):
        ensure_native_bar_coverage(
            _request(ref),
            provider=GapFillProvider.YFINANCE,
            locators={ref: "ES"},
            store_dir=tmp_path,
        )
