"""YFinance listed-instrument Pulls (aegis-data)."""

from __future__ import annotations

import pandas as pd
import pytest
from aegis_runtime import FuturesRef, ListedRef

from aegis_data.calendars import TradingCalendar
from aegis_data.store import (
    CoveredWindow,
    FxPair,
    HistoricalStore,
    NativeBarsRequest,
    StoreAdmissionError,
    StoreCoverageError,
)
from aegis_data.pull import FetchWindow
from aegis_data.yfinance import (
    YFinanceLocator,
    pull_yfinance_fx_history,
    pull_yfinance_native_bars,
    yfinance_fx_adapter,
    yfinance_native_adapter,
)


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


def _multi_index_yfinance_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            ("Open", "SPY"): [100.0, 101.0],
            ("High", "SPY"): [101.0, 102.0],
            ("Low", "SPY"): [99.0, 100.0],
            ("Close", "SPY"): [100.5, 101.5],
            ("Adj Close", "SPY"): [90.5, 91.5],
            ("Volume", "SPY"): [1000, 1100],
        },
        index=pd.DatetimeIndex(
            ["2024-01-02 16:00:00", "2024-01-03 16:00:00"],
            tz="America/New_York",
        ),
    )


def _native_fetch_window(*, arrays: tuple[str, ...] = ("Close",)) -> FetchWindow:
    return FetchWindow(
        timeframe="1D",
        start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-04"),
        arrays=arrays,
    )


def _fx_fetch_window() -> FetchWindow:
    return FetchWindow(
        timeframe="1D",
        start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-04"),
        arrays=("rate",),
    )


def _listed_window(
    *,
    arrays: tuple[str, ...],
    start: str = "2024-01-02",
    end: str = "2024-01-05",
) -> CoveredWindow:
    return CoveredWindow(
        timeframe="1D",
        start=start,
        end=end,
        arrays=arrays,
        calendar=TradingCalendar.XNYS,
    )


def _fx_window(
    *,
    start: str = "2024-01-02",
    end: str = "2024-01-05",
) -> CoveredWindow:
    return CoveredWindow(
        timeframe="1D",
        start=start,
        end=end,
        arrays=("rate",),
        calendar=TradingCalendar.WEEKDAY,
    )


def test_yfinance_native_adapter_binds_locator() -> None:
    calls: list[str] = []

    def fetch(locator: YFinanceLocator, window: FetchWindow) -> pd.DataFrame:
        calls.append(locator.ticker)
        return _multi_index_yfinance_bars()

    adapter = yfinance_native_adapter(YFinanceLocator("SPY"), fetcher=fetch)
    adapter(_native_fetch_window())

    assert calls == ["SPY"]


def test_yfinance_native_adapter_normalizes_single_symbol_multi_index() -> None:
    adapter = yfinance_native_adapter(
        YFinanceLocator("SPY"),
        fetcher=lambda _locator, _window: _multi_index_yfinance_bars(),
    )

    frame = adapter(_native_fetch_window())

    assert frame.index.tolist() == [
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
    ]
    assert frame["Close"].tolist() == [100.5, 101.5]


def test_yfinance_native_adapter_selects_requested_arrays() -> None:
    adapter = yfinance_native_adapter(
        YFinanceLocator("SPY"),
        fetcher=lambda _locator, _window: _multi_index_yfinance_bars(),
    )

    frame = adapter(_native_fetch_window(arrays=("Close", "Adj Close")))

    assert frame.columns.tolist() == [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "Adj Close",
    ]
    assert frame["Adj Close"].tolist() == [90.5, 91.5]


def test_yfinance_pull_writes_native_bars_under_listed_ref_not_locator(
    tmp_path,
) -> None:
    ref = ListedRef("BBG000B9XRY4")
    store = HistoricalStore(tmp_path)
    calls: list[str] = []

    def fetch(locator: YFinanceLocator, _window: FetchWindow) -> pd.DataFrame:
        calls.append(locator.ticker)
        return _bars(100.0)

    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Open", "High", "Low", "Close", "Volume"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
    )

    pull_yfinance_native_bars(
        request, YFinanceLocator("BRK-B"), fetcher=fetch, store_dir=tmp_path
    )
    pull_yfinance_native_bars(
        request, YFinanceLocator("BRK.B"), fetcher=fetch, store_dir=tmp_path
    )

    frame = store.read(ref, _listed_window(arrays=("Close",)))

    assert calls == ["BRK-B"]
    assert frame["Close"].tolist() == [100.0, 101.0, 102.0]


def test_yfinance_pull_keeps_close_raw_and_stores_adj_close_only_when_requested(
    tmp_path,
) -> None:
    ref = ListedRef("BBG000B9XRY4")
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Open", "High", "Low", "Close", "Volume"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
    )

    pull_yfinance_native_bars(
        request,
        YFinanceLocator("SPY"),
        fetcher=lambda _locator, _window: _bars_with_adj_close(),
        store_dir=tmp_path,
    )
    store = HistoricalStore(tmp_path)
    frame = store.read(ref, _listed_window(arrays=("Close",)))

    assert frame["Close"].tolist() == [100.0, 101.0, 102.0]
    with pytest.raises(StoreCoverageError, match="Adj Close"):
        store.read(ref, _listed_window(arrays=("Adj Close",)))


def test_yfinance_pull_stores_requested_adj_close_as_separate_array(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Close", "Adj Close"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
    )

    pull_yfinance_native_bars(
        request,
        YFinanceLocator("SPY"),
        fetcher=lambda _locator, _window: _bars_with_adj_close(),
        store_dir=tmp_path,
    )
    frame = HistoricalStore(tmp_path).read(
        ref,
        _listed_window(arrays=("Close", "Adj Close")),
    )

    assert frame["Close"].tolist() == [100.0, 101.0, 102.0]
    assert frame["Adj Close"].tolist() == [90.0, 91.0, 92.0]


def test_yfinance_pull_rejects_missing_requested_adj_close(tmp_path) -> None:
    ref = ListedRef("BBG000B9XRY4")
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Close", "Adj Close"),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
    )

    with pytest.raises(StoreAdmissionError, match="Adj Close"):
        pull_yfinance_native_bars(
            request,
            YFinanceLocator("SPY"),
            fetcher=lambda _locator, _window: _bars(100.0),
            store_dir=tmp_path,
        )

    with pytest.raises(StoreCoverageError, match="2024-01-02"):
        HistoricalStore(tmp_path).read(ref, _listed_window(arrays=("Close",)))


def test_yfinance_fx_adapter_binds_locator() -> None:
    calls: list[str] = []

    def fetch(locator: YFinanceLocator, _window: FetchWindow) -> pd.DataFrame:
        calls.append(locator.ticker)
        return pd.DataFrame(
            {"Close": [1.10]},
            index=pd.DatetimeIndex(["2024-01-02"]),
        )

    adapter = yfinance_fx_adapter(YFinanceLocator("EURUSD=X"), fetcher=fetch)
    adapter(_fx_fetch_window())

    assert calls == ["EURUSD=X"]


def test_yfinance_fx_adapter_fetches_provider_close_privately() -> None:
    requested_arrays: list[tuple[str, ...]] = []

    def fetch(_locator: YFinanceLocator, window: FetchWindow) -> pd.DataFrame:
        requested_arrays.append(tuple(window.arrays))
        return pd.DataFrame(
            {"Close": [1.10]},
            index=pd.DatetimeIndex(["2024-01-02"]),
        )

    adapter = yfinance_fx_adapter(YFinanceLocator("EURUSD=X"), fetcher=fetch)
    adapter(_fx_fetch_window())

    assert requested_arrays == [("Close",)]


def test_yfinance_fx_adapter_converts_close_to_rate_frame() -> None:
    adapter = yfinance_fx_adapter(
        YFinanceLocator("EURUSD=X"),
        fetcher=lambda _locator, _window: pd.DataFrame(
            {"Close": [1.10, 1.11]},
            index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"]),
        ),
    )

    frame = adapter(_fx_fetch_window())

    assert frame.columns.tolist() == ["rate"]
    assert frame["rate"].tolist() == [1.10, 1.11]


def test_yfinance_fx_adapter_rejects_missing_close() -> None:
    adapter = yfinance_fx_adapter(
        YFinanceLocator("EURUSD=X"),
        fetcher=lambda _locator, _window: pd.DataFrame(
            {"Open": [1.10]},
            index=pd.DatetimeIndex(["2024-01-02"]),
        ),
    )

    with pytest.raises(ValueError, match="missing Close"):
        adapter(_fx_fetch_window())


def test_yfinance_fx_pull_writes_fx_history_under_pair_identity(tmp_path) -> None:
    pair = FxPair("EUR", "USD")
    calls: list[tuple[str, str, str]] = []

    def fetch(locator: YFinanceLocator, window: FetchWindow) -> pd.DataFrame:
        calls.append((locator.ticker, str(window.start), str(window.end)))
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
        calendar=TradingCalendar.WEEKDAY,
    )
    rates = HistoricalStore(tmp_path).read(pair, _fx_window())["rate"]

    assert calls == [("EURUSD=X", "2024-01-02 00:00:00", "2024-01-05 00:00:00")]
    assert rates.tolist() == [1.10, 1.11, 1.12]


def test_yfinance_pull_requires_one_explicit_listed_ref(tmp_path) -> None:
    request = NativeBarsRequest(
        refs=(FuturesRef("ES", "GLBX.MDP3"),),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
    )

    with pytest.raises(TypeError, match="ListedRef"):
        pull_yfinance_native_bars(
            request,
            YFinanceLocator("ES=F"),
            fetcher=lambda _locator, _window: _bars(100.0),
            store_dir=tmp_path,
        )
