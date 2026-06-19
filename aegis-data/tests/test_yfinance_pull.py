"""YFinance listed-instrument Pulls (aegis-data)."""

from __future__ import annotations

import pandas as pd
import pytest
from aegis_runtime import FuturesRef, ListedRef

from aegis_data.store import (
    FxPair,
    NativeBarsRequest,
    StoreAdmissionError,
    StoreCoverageError,
    fx_history_path,
    native_bars_path,
    read_fx_history,
    read_native_bars,
    write_fx_history,
    write_native_bars,
)
from aegis_data.yfinance import YFinanceLocator, pull_yfinance_fx_history, pull_yfinance_native_bars


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


def _bars_with_adj_close() -> pd.DataFrame:
    bars = _bars(100.0)
    bars["Adj Close"] = [90.0, 91.0, 92.0]
    return bars


def test_yfinance_pull_writes_native_bars_under_listed_ref_not_locator(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    calls: list[str] = []

    def fetch(locator: YFinanceLocator, _request: NativeBarsRequest) -> pd.DataFrame:
        calls.append(locator.ticker)
        return _bars(100.0)

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

    assert calls == ["BRK-B"]
    assert frames[ref]["Close"].tolist() == [100.0, 101.0, 102.0]
    assert sorted(path.name for path in (tmp_path / "listed").iterdir()) == ["BBG000B9XRY4"]


def test_yfinance_pull_fetches_only_uncovered_calendar_gaps(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    existing = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [100.0, 101.0, 102.0],
            "Low": [100.0, 101.0, 102.0],
            "Close": [100.0, 101.0, 102.0],
            "Volume": [1000, 1100, 1200],
        },
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )
    fetched = pd.DataFrame(
        {
            "Open": [103.0, 104.0],
            "High": [103.0, 104.0],
            "Low": [103.0, 104.0],
            "Close": [103.0, 104.0],
            "Volume": [1300, 1400],
        },
        index=pd.DatetimeIndex(["2024-01-05", "2024-01-08"]),
    )
    calls: list[tuple[str, str]] = []

    def fetch(_locator: YFinanceLocator, request: NativeBarsRequest) -> pd.DataFrame:
        calls.append((str(request.start), str(request.end)))
        return fetched

    write_native_bars(ref, "1D", existing, store_dir=tmp_path)
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Open", "High", "Low", "Close", "Volume"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-09",
    )

    pull_yfinance_native_bars(request, YFinanceLocator("SPY"), fetcher=fetch, store_dir=tmp_path)
    frames = read_native_bars(
        (ref,),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-09",
        store_dir=tmp_path,
    )

    assert calls == [("2024-01-05 00:00:00", "2024-01-09 00:00:00")]
    assert frames[ref]["Close"].tolist() == [100.0, 101.0, 102.0, 103.0, 104.0]


def test_yfinance_pull_fetches_existing_dates_when_requested_array_is_uncovered(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    calls: list[tuple[str, str]] = []

    def fetch(_locator: YFinanceLocator, request: NativeBarsRequest) -> pd.DataFrame:
        calls.append((str(request.start), str(request.end)))
        return _bars_with_adj_close()

    write_native_bars(ref, "1D", _bars(100.0), store_dir=tmp_path)
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Close", "Adj Close"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
    )

    pull_yfinance_native_bars(request, YFinanceLocator("SPY"), fetcher=fetch, store_dir=tmp_path)
    frames = read_native_bars(
        (ref,),
        arrays=("Close", "Adj Close"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        store_dir=tmp_path,
    )

    assert calls == [("2024-01-02 00:00:00", "2024-01-05 00:00:00")]
    assert frames[ref]["Close"].tolist() == [100.0, 101.0, 102.0]
    assert frames[ref]["Adj Close"].tolist() == [90.0, 91.0, 92.0]


def test_yfinance_pull_rejects_missing_expected_session_before_writing(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    incomplete = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [100.0],
            "Low": [100.0],
            "Close": [100.0],
            "Volume": [1000],
        },
        index=pd.DatetimeIndex(["2024-03-28"]),
    )
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Open", "High", "Low", "Close", "Volume"),
        timeframe="1D",
        start="2024-03-28",
        end="2024-04-02",
    )

    with pytest.raises(StoreAdmissionError, match="2024-04-01"):
        pull_yfinance_native_bars(
            request,
            YFinanceLocator("SPY"),
            fetcher=lambda _locator, _request: incomplete,
            store_dir=tmp_path,
        )

    assert not native_bars_path(ref, "1D", store_dir=tmp_path).exists()


def test_yfinance_pull_keeps_close_raw_and_stores_adj_close_only_when_requested(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Open", "High", "Low", "Close", "Volume"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
    )

    pull_yfinance_native_bars(
        request,
        YFinanceLocator("SPY"),
        fetcher=lambda _locator, _request: _bars_with_adj_close(),
        store_dir=tmp_path,
    )
    frames = read_native_bars(
        (ref,),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        store_dir=tmp_path,
    )

    assert frames[ref]["Close"].tolist() == [100.0, 101.0, 102.0]
    with pytest.raises(StoreCoverageError, match="Adj Close"):
        read_native_bars(
            (ref,),
            arrays=("Adj Close",),
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            store_dir=tmp_path,
        )


def test_yfinance_pull_stores_requested_adj_close_as_separate_array(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Close", "Adj Close"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
    )

    pull_yfinance_native_bars(
        request,
        YFinanceLocator("SPY"),
        fetcher=lambda _locator, _request: _bars_with_adj_close(),
        store_dir=tmp_path,
    )
    frames = read_native_bars(
        (ref,),
        arrays=("Close", "Adj Close"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        store_dir=tmp_path,
    )

    assert frames[ref]["Close"].tolist() == [100.0, 101.0, 102.0]
    assert frames[ref]["Adj Close"].tolist() == [90.0, 91.0, 92.0]


def test_yfinance_pull_rejects_missing_requested_adj_close(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Close", "Adj Close"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
    )

    with pytest.raises(StoreAdmissionError, match="Adj Close"):
        pull_yfinance_native_bars(
            request,
            YFinanceLocator("SPY"),
            fetcher=lambda _locator, _request: _bars(100.0),
            store_dir=tmp_path,
        )

    assert not native_bars_path(ref, "1D", store_dir=tmp_path).exists()


def test_yfinance_fx_pull_writes_fx_history_under_pair_identity(tmp_path) -> None:
    pair = FxPair("EUR", "USD")
    calls: list[tuple[str, str, str]] = []

    def fetch(locator: YFinanceLocator, request: NativeBarsRequest) -> pd.DataFrame:
        calls.append((locator.ticker, str(request.start), str(request.end)))
        return pd.DataFrame(
            {"Close": [1.10, 1.11, 1.12]},
            index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
        )

    pull_yfinance_fx_history(
        pair,
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        locator=YFinanceLocator("EURUSD=X"),
        fetcher=fetch,
        store_dir=tmp_path,
    )
    rates = read_fx_history(
        (pair,),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        store_dir=tmp_path,
    )

    assert calls == [("EURUSD=X", "2024-01-02 00:00:00", "2024-01-05 00:00:00")]
    assert rates[pair].tolist() == [1.10, 1.11, 1.12]


def test_yfinance_fx_pull_fetches_only_uncovered_rate_gaps(tmp_path) -> None:
    pair = FxPair("EUR", "USD")
    calls: list[tuple[str, str]] = []
    write_fx_history(
        pair,
        "1D",
        pd.Series([1.10], index=pd.DatetimeIndex(["2024-01-02"])),
        store_dir=tmp_path,
    )

    def fetch(_locator: YFinanceLocator, request: NativeBarsRequest) -> pd.DataFrame:
        calls.append((str(request.start), str(request.end)))
        return pd.DataFrame(
            {"Close": [1.11, 1.12]},
            index=pd.DatetimeIndex(["2024-01-03", "2024-01-04"]),
        )

    pull_yfinance_fx_history(
        pair,
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        locator=YFinanceLocator("EURUSD=X"),
        fetcher=fetch,
        store_dir=tmp_path,
    )
    rates = read_fx_history(
        (pair,),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        store_dir=tmp_path,
    )

    assert calls == [("2024-01-03 00:00:00", "2024-01-05 00:00:00")]
    assert rates[pair].tolist() == [1.10, 1.11, 1.12]


def test_yfinance_fx_pull_rejects_missing_expected_rate_before_writing(tmp_path) -> None:
    pair = FxPair("EUR", "USD")
    incomplete = pd.DataFrame({"Close": [1.10]}, index=pd.DatetimeIndex(["2024-01-02"]))

    with pytest.raises(StoreAdmissionError, match="2024-01-03"):
        pull_yfinance_fx_history(
            pair,
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            locator=YFinanceLocator("EURUSD=X"),
            fetcher=lambda _locator, _request: incomplete,
            store_dir=tmp_path,
        )

    assert not fx_history_path(pair, "1D", store_dir=tmp_path).exists()


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
