"""Ensure Coverage Pull dispatch (aegis-data).

These tests pin the asset-class dispatch matrix that used to live in the RD store
adapter: which Pull runs for each ``(InstrumentRef, GapFillProvider)`` pair, and
how Provider Locators flow to the providers that need them.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from aegis_runtime import FuturesRef, ListedRef

from aegis_data.calendars import TradingCalendar
from aegis_data.coverage import GapFillProvider, ensure_native_bar_coverage
from aegis_data.roll import DatedContract
from aegis_data.store import (
    NativeBarsRequest,
    native_bars_path,
    read_native_bars,
    write_native_bars,
)
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


# --- behaviour: observable outcomes through the Ensure Coverage -> Store seam ---


def _window_request(ref: object, *, start: str, end: str) -> NativeBarsRequest:
    return NativeBarsRequest(
        refs=(ref,),
        arrays=_ARRAYS,
        timeframe="1D",
        start=start,
        end=end,
        calendar=TradingCalendar.XNYS,
    )


def _bars_for(dates: list[str], base: float) -> pd.DataFrame:
    closes = [base + offset for offset in range(len(dates))]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 1.0 for value in closes],
            "Low": [value - 1.0 for value in closes],
            "Close": closes,
            "Volume": [1000.0] * len(dates),
        },
        index=pd.DatetimeIndex(dates),
    )


def test_ensure_coverage_fetches_only_the_uncovered_gap_and_keeps_existing_bars(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A second Ensure over a wider window pulls only the new day, additively."""
    ref = ListedRef("BBG000B9XRY4")
    master = _bars_for(["2024-01-02", "2024-01-03", "2024-01-04"], 10.0)
    windows: list[tuple[str, str]] = []

    def fetch(_locator: YFinanceLocator, window: FetchWindow) -> pd.DataFrame:
        windows.append(
            (
                pd.Timestamp(window.start).date().isoformat(),
                pd.Timestamp(window.end).date().isoformat(),
            )
        )
        start = pd.Timestamp(window.start)
        end = pd.Timestamp(window.end)
        return master.loc[(master.index >= start) & (master.index < end)]

    monkeypatch.setattr("aegis_data.yfinance._fetch_yfinance", fetch)

    ensure_native_bar_coverage(
        _window_request(ref, start="2024-01-02", end="2024-01-04"),
        provider=GapFillProvider.YFINANCE,
        locators={ref: "BRK-B"},
        store_dir=tmp_path,
    )
    ensure_native_bar_coverage(
        _window_request(ref, start="2024-01-02", end="2024-01-05"),
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
    # First Ensure pulled [2,4); the second pulled only the missing [4,5) day.
    assert windows == [("2024-01-02", "2024-01-04"), ("2024-01-04", "2024-01-05")]
    assert frames[ref]["Close"].tolist() == [10.0, 11.0, 12.0]


def test_ensure_coverage_does_not_fetch_when_window_is_already_covered(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ref = ListedRef("BBG000B9XRY4")
    write_native_bars(
        ref,
        "1D",
        _bars_for(["2024-01-02", "2024-01-03", "2024-01-04"], 10.0),
        required_arrays=("Close",),
        store_dir=tmp_path,
    )

    def fetch(_locator: YFinanceLocator, _window: FetchWindow) -> pd.DataFrame:
        raise AssertionError("Ensure Coverage fetched a provider for an already-covered window")

    monkeypatch.setattr("aegis_data.yfinance._fetch_yfinance", fetch)

    ensure_native_bar_coverage(
        _window_request(ref, start="2024-01-02", end="2024-01-05"),
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
    assert frames[ref]["Close"].tolist() == [10.0, 11.0, 12.0]


def test_ensure_coverage_stores_each_ref_under_its_figi_not_its_locator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Two refs with distinct tickers each read back their own bars, keyed by FIGI."""
    first = ListedRef("BBG000B9XRY4")
    second = ListedRef("BBG000BPH459")
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    bars_by_ticker = {"BRK-B": _bars_for(dates, 10.0), "MSFT": _bars_for(dates, 400.0)}

    def fetch(locator: YFinanceLocator, _window: FetchWindow) -> pd.DataFrame:
        return bars_by_ticker[locator.ticker]

    monkeypatch.setattr("aegis_data.yfinance._fetch_yfinance", fetch)

    ensure_native_bar_coverage(
        _request(first, second),
        provider=GapFillProvider.YFINANCE,
        locators={first: "BRK-B", second: "MSFT"},
        store_dir=tmp_path,
    )

    frames = read_native_bars(
        (first, second),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
        store_dir=tmp_path,
    )
    assert frames[first]["Close"].tolist() == [10.0, 11.0, 12.0]
    assert frames[second]["Close"].tolist() == [400.0, 401.0, 402.0]
    # Identity, not provider locator: bars live under the FIGI directory.
    assert native_bars_path(first, "1D", store_dir=tmp_path).exists()
    assert sorted(p.name for p in (tmp_path / "listed").iterdir()) == [
        "BBG000B9XRY4",
        "BBG000BPH459",
    ]


_FUTURES_BASIS = {"ESH4": 100.0, "ESM4": 200.0, "ESU4": 300.0, "ESZ4": 400.0}


def _leg_bars(symbol: str, start: date, end: date) -> pd.DataFrame:
    index = pd.bdate_range(start, end)
    closes = [_FUTURES_BASIS[symbol] + offset for offset in range(len(index))]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 1.0 for value in closes],
            "Low": [value - 1.0 for value in closes],
            "Close": closes,
            "Volume": [1000.0] * len(index),
        },
        index=index,
    )


def _es_calendar(root: str, start: date, end: date) -> list[DatedContract]:
    return [
        DatedContract("ESH4", date(2024, 3, 15)),
        DatedContract("ESM4", date(2024, 6, 21)),
        DatedContract("ESU4", date(2024, 9, 20)),
        DatedContract("ESZ4", date(2024, 12, 20)),
    ]


def test_ensure_coverage_materializes_readable_continuous_futures_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The futures dispatch yields covered, readable continuous history end-to-end."""
    ref = FuturesRef("ES", "GLBX.MDP3", roll_rule="calendar", adjustment="back_adjust")
    monkeypatch.setattr(
        "aegis_data.databento_pull.databento_port_fetcher",
        lambda _dataset, *, client=None: _leg_bars,
    )
    monkeypatch.setattr(
        "aegis_data.databento_pull.databento_contract_calendar",
        lambda _dataset, *, client=None: _es_calendar,
    )

    ensure_native_bar_coverage(
        _window_request(ref, start="2024-01-02", end="2025-01-01"),
        provider=GapFillProvider.DATABENTO,
        locators={ref: "ES"},
        store_dir=tmp_path,
    )

    frames = read_native_bars(
        (ref,),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2025-01-01",
        calendar=TradingCalendar.XNYS,
        store_dir=tmp_path,
    )
    close = frames[ref]["Close"]
    assert not close.isna().any()
    assert len(close) > 200  # a full year of XNYS sessions, gap-free
