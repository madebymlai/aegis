from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pandas as pd
import pytest
from aegis_data.calendars import TradingCalendar
from aegis_data.pull import FetchWindow
from aegis_data.store import CoveredWindow, HistoricalStore, NativeBarsRequest, WriteMode
from aegis_data.yfinance import YFinanceLocator, pull_yfinance_native_bars
from aegis_runtime import FuturesRef, ListedRef
from vectorbtpro import vbt

from research.aegis_research.data import load_market_data_result
from research.aegis_research.market_data.adapters import csv as csv_adapter
from research.aegis_research.market_data.adapters import remote as remote_adapter
from research.aegis_research.market_data.adapters import synthetic as synthetic_adapter
from research.aegis_research.market_data.adapters.store import reconcile_panels
from research.aegis_research.market_data.contracts import (
    MarketDataAdapterResult,
    RemoteDataPullError,
)
from research.aegis_research.run_pipeline import _load_fx_rates
from tests.support.research.aegis_research.factories import make_data_config


def _pulled_bars_with_adj_close() -> pd.DataFrame:
    index = pd.bdate_range("2024-01-02", periods=3)
    return pd.DataFrame(
        {
            "Open": [9.0, 10.0, 11.0],
            "High": [10.0, 11.0, 12.0],
            "Low": [8.0, 9.0, 10.0],
            "Close": [100.0, 101.0, 102.0],
            "Adj Close": [90.0, 91.0, 92.0],
            "Volume": [1000, 1100, 1200],
        },
        index=index,
    )


_MIXED_SIGNAL_ES = FuturesRef("ES", "GLBX.MDP3", "calendar", "backward_ratio")
_MIXED_SIGNAL_BZ = FuturesRef("BZ", "IFEU.IMPACT", "calendar", "backward_ratio")
_MIXED_PNL_BZ = FuturesRef("BZ", "IFEU.IMPACT", "calendar", "backward_spread")
_MIXED_DATASET_INDEX = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])
_MIXED_DATASET_VALUES = {
    _MIXED_SIGNAL_ES: [1.0, 2.0, 3.0],
    _MIXED_SIGNAL_BZ: [10.0, 20.0, 30.0],
    _MIXED_PNL_BZ: [100.0, 200.0, 300.0],
}


def _store(store_dir: Path | None) -> HistoricalStore:
    return HistoricalStore(store_dir) if store_dir is not None else HistoricalStore()


def _write_store_bars(
    ref,
    bars: pd.DataFrame,
    *,
    store_dir: Path | None,
    arrays: tuple[str, ...] = ("Close",),
    timeframe: str = "1D",
) -> None:
    end = bars.index.max() + pd.Timedelta(days=1)
    _store(store_dir).write(
        ref,
        bars,
        CoveredWindow(
            timeframe=timeframe,
            start=bars.index.min(),
            end=end,
            arrays=arrays,
            calendar=TradingCalendar.XNYS,
        ),
        mode=WriteMode.OVERWRITE,
    )


class _RecordingMixedDatasetPull:
    def __init__(self) -> None:
        self.requests: list[NativeBarsRequest] = []

    def __call__(self, request: NativeBarsRequest, *, store_dir=None) -> object:
        self.requests.append(request)
        _write_mixed_dataset_bars(request, store_dir=store_dir)
        return object()


def _write_mixed_dataset_bars(
    request: NativeBarsRequest,
    *,
    store_dir: Path | None,
) -> None:
    for ref in request.refs:
        _write_store_bars(
            ref,
            pd.DataFrame(
                {"Close": _MIXED_DATASET_VALUES[ref]},
                index=_MIXED_DATASET_INDEX,
            ),
            store_dir=store_dir,
        )


def _mixed_dataset_store_config():
    return make_data_config(
        source="store",
        provider="databento",
        symbols=[
            {
                "root": "ES",
                "ccy": "USD",
                "dataset": "GLBX.MDP3",
                "adjustment": "backward_ratio",
            },
            {
                "root": "BZ",
                "ccy": "USD",
                "dataset": "IFEU.IMPACT",
                "adjustment": "backward_ratio",
                "pnl_adjustment": "backward_spread",
            },
        ],
        arrays=["Close"],
        start="2024-01-02",
        end="2024-01-05",
    )


def test_reconcile_panels_forward_fills_a_closed_day_and_trims_leading_warmup() -> None:
    # aegis-rd-z5l: _array_panels unions each root's OWN trading days, so a day root AAA trades
    # but root BBB is closed (cross-venue holiday divergence / a thin contract's no-trade day)
    # lands as a NaN cell -- a closed market, not a hole in the price process. Reconciliation:
    #  - forward-fills the interior gap as a FLAT no-trade bar: carry BBB's last settle (Close)
    #    into every price array -> a doji at the prior close (0 return, NO fabricated intraday
    #    range), Volume 0; and
    #  - trims the leading NaN (BBB's first bar is a day after AAA's) to the common warm-up,
    #    never back-filling a price that never existed,
    # leaving no surviving NaN for the quality gate.
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])

    def panel(aaa: list[float], bbb: list[float | None]) -> pd.DataFrame:
        return pd.DataFrame({"AAA": aaa, "BBB": bbb}, index=index)

    panels = {  # BBB: leading NaN on 01-02, interior (closed) NaN on 01-04
        "Open": panel([9.0, 10.0, 11.0, 12.0], [None, 19.0, None, 21.0]),
        "High": panel([11.0, 12.0, 13.0, 14.0], [None, 21.0, None, 23.0]),
        "Low": panel([8.0, 9.0, 10.0, 11.0], [None, 18.0, None, 20.0]),
        "Close": panel([10.0, 11.0, 12.0, 13.0], [None, 20.0, None, 22.0]),
        "Volume": panel([100.0, 110.0, 120.0, 130.0], [None, 200.0, None, 220.0]),
    }

    out = reconcile_panels(panels)

    # Leading warm-up trimmed: the panel starts at BBB's first real bar (the common warm-up day).
    expected_index = pd.DatetimeIndex(["2024-01-03", "2024-01-04", "2024-01-05"])
    for name, frame in out.items():
        assert list(frame.index) == list(expected_index), name
        assert int(frame.isna().sum().sum()) == 0, name  # no surviving NaN anywhere
    # BBB's closed day (01-04) is a flat doji at its last settle (01-03 Close == 20), volume 0.
    closed = pd.Timestamp("2024-01-04")
    assert out["Close"].loc[closed, "BBB"] == 20.0  # carried settle -> 0 return
    assert out["Open"].loc[closed, "BBB"] == 20.0  # the settle, NOT the prior Open (19)
    assert out["High"].loc[closed, "BBB"] == 20.0  # the settle, NOT the prior High (21): no fake range
    assert out["Low"].loc[closed, "BBB"] == 20.0
    assert out["Volume"].loc[closed, "BBB"] == 0.0
    # AAA traded that day -- untouched.
    assert out["Close"].loc[closed, "AAA"] == 12.0
    assert out["Volume"].loc[closed, "AAA"] == 120.0


def test_synthetic_adapter_loads_native_data_behind_the_seam() -> None:
    result = synthetic_adapter.load_synthetic_source(
        make_data_config(source="synthetic", rows=4, symbols=[{"ticker": "AAA", "ccy": "EUR"}, {"ticker": "BBB", "ccy": "EUR"}])
    )

    assert isinstance(result, MarketDataAdapterResult)
    assert result.native_data.feature_oriented
    assert result.source_metadata == {"generated": True, "seed": 42, "rows": 4}
    assert result.evidence["source"] == "generated"


def test_csv_adapter_loads_flat_feature_columns(tmp_path: Path) -> None:
    path = tmp_path / "prices.csv"
    frame = pd.DataFrame(
        {"Open": [1.0, 2.0, 3.0], "Close": [1.5, 2.5, 3.5]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC", name="time"),
    )
    frame.to_csv(path)

    result = csv_adapter.load_csv_source(
        make_data_config(source="csv", path=str(path), symbols=[{"ticker": "SYN", "ccy": "EUR"}], arrays=["Open", "Close"])
    )

    assert isinstance(result, MarketDataAdapterResult)
    assert result.source_metadata == {"path": "<redacted>", "layout": "flat"}
    assert result.evidence["source"] == "csv_raw"


def test_describe_consumes_pre_scrubbed_provider_metadata_from_the_adapter() -> None:
    native_data = _LeakyProviderData()

    result = load_market_data_result(
        make_data_config(source="prescrubbed", symbols=[{"ticker": "SYN", "ccy": "EUR"}], arrays=["Close"]),
        adapters={
            "prescrubbed": lambda _config: MarketDataAdapterResult(
                native_data=native_data,
                provider_metadata={"source": "prescrubbed", "fetch_kwargs": {"period": "1mo"}},
                omitted_metadata_fields=[
                    {"path": "fetch_kwargs.api_key", "reason": "secret-like or denied key"}
                ],
            )
        },
    )

    assert result.metadata.provenance.provider_metadata == {
        "source": "prescrubbed",
        "fetch_kwargs": {"period": "1mo"},
    }
    assert result.metadata.provenance.omitted_metadata_fields == [
        {"path": "fetch_kwargs.api_key", "reason": "secret-like or denied key"}
    ]


def test_remote_adapter_projects_allowlisted_provider_mappings() -> None:
    config = make_data_config(source="fakeremote", symbols=[{"ticker": "SYN", "ccy": "EUR"}], arrays=["Close"])

    result = remote_adapter.load_vbt_remote_source("fakeremote", _FakeRemoteData, config)

    assert result.provider_metadata["fetch_kwargs"] == {"period": "1mo", "limit": 100}
    assert result.provider_metadata["returned_kwargs"] == {"freq": "1D"}
    assert {item["path"] for item in result.omitted_metadata_fields} >= {
        "fetch_kwargs.headers",
        "fetch_kwargs.cache_path",
        "returned_kwargs.auth",
    }


def test_store_adapter_pulls_missing_yfinance_gap_then_reads_by_figi(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    ref = ListedRef("BBG000B9XRY4")
    _write_store_bars(
        ref,
        pd.DataFrame(
            {"Open": [10.0], "High": [10.0], "Low": [10.0], "Close": [10.0], "Volume": [1000]},
            index=pd.DatetimeIndex(["2024-01-02"]),
        ),
        store_dir=None,
    )
    requests: list[tuple[str, str, str]] = []

    def fetch_gap(locator: YFinanceLocator, window: FetchWindow) -> pd.DataFrame:
        requests.append(
            (
                locator.ticker,
                pd.Timestamp(window.start).date().isoformat(),
                pd.Timestamp(window.end).date().isoformat(),
            )
        )
        return pd.DataFrame(
            {
                "Open": [11.0, 12.0],
                "High": [11.0, 12.0],
                "Low": [11.0, 12.0],
                "Close": [11.0, 12.0],
                "Volume": [1100, 1200],
            },
            index=pd.DatetimeIndex(["2024-01-03", "2024-01-04"]),
        )

    monkeypatch.setattr("aegis_data.yfinance._fetch_yfinance", fetch_gap)
    config = make_data_config(
        source="store",
        provider="yfinance",
        symbols=[{"ticker": "BRK-B", "ccy": "USD", "figi": ref.figi}],
        arrays=["Close"],
        start="2024-01-02",
        end="2024-01-05",
    )

    result = load_market_data_result(config)

    assert requests == [("BRK-B", "2024-01-03", "2024-01-05")]
    assert result.metadata.provenance.index_evidence["source"] == "aegis_data_store"
    assert list(result.native_data.get(feature="Close").columns) == ["BRK-B"]
    assert result.native_data.get(feature="Close")["BRK-B"].tolist() == [10.0, 11.0, 12.0]


def test_store_adapter_reads_listed_covered_history_by_figi(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    ref = ListedRef("BBG000B9XRY4")
    index = pd.bdate_range("2024-01-02", periods=3)
    pulled = pd.DataFrame(
        {
            "Open": [10.0, 11.0, 12.0],
            "High": [10.0, 11.0, 12.0],
            "Low": [10.0, 11.0, 12.0],
            "Close": [10.0, 11.0, 12.0],
            "Volume": [1000, 1100, 1200],
        },
        index=index,
    )
    request = NativeBarsRequest(
        refs=(ref,),
        arrays=("Close",),
        timeframe="1D",
        start="2024-01-02",
        end="2024-01-05",
        calendar=TradingCalendar.XNYS,
    )
    pull_yfinance_native_bars(
        request,
        YFinanceLocator("BRK-B"),
        fetcher=lambda _locator, _window: pulled,
    )
    config = make_data_config(
        source="store",
        provider="yfinance",
        symbols=[{"ticker": "BRK-B", "ccy": "USD", "figi": ref.figi}],
        arrays=["Close"],
        start="2024-01-02",
        end="2024-01-05",
    )

    result = load_market_data_result(config)

    assert result.metadata.provenance.index_evidence["source"] == "aegis_data_store"
    assert list(result.native_data.get(feature="Close").columns) == ["BRK-B"]
    assert result.native_data.get(feature="Close")["BRK-B"].tolist() == [10.0, 11.0, 12.0]


def test_store_adapter_reads_raw_close_not_unrequested_adj_close(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    ref = ListedRef("BBG000B9XRY4")
    pulled = _pulled_bars_with_adj_close()
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
        fetcher=lambda _locator, _window: pulled,
    )
    config = make_data_config(
        source="store",
        provider="yfinance",
        symbols=[{"ticker": "SPY", "ccy": "USD", "figi": ref.figi}],
        arrays=["Close"],
        start="2024-01-02",
        end="2024-01-05",
    )

    result = load_market_data_result(config)

    assert list(result.native_data.get(feature="Close").columns) == ["SPY"]
    assert result.native_data.get(feature="Close")["SPY"].tolist() == [100.0, 101.0, 102.0]


def test_store_adapter_reads_requested_adj_close_through_aegis_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    ref = ListedRef("BBG000B9XRY4")
    pulled = _pulled_bars_with_adj_close()
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
        fetcher=lambda _locator, _window: pulled,
    )
    config = make_data_config(
        source="store",
        provider="yfinance",
        symbols=[{"ticker": "SPY", "ccy": "USD", "figi": ref.figi}],
        arrays=["Close", "Adj Close"],
        start="2024-01-02",
        end="2024-01-05",
    )

    result = load_market_data_result(config)

    assert result.native_data.get(feature="Close")["SPY"].tolist() == [100.0, 101.0, 102.0]
    assert result.native_data.get(feature="Adj Close")["SPY"].tolist() == [90.0, 91.0, 92.0]


def test_store_adapter_reads_per_symbol_dataset_for_futures_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    ref = FuturesRef("ES", "GLBX.MDP3", "calendar", "unadjusted")
    requests: list[NativeBarsRequest] = []

    def pull_futures(request: NativeBarsRequest, *, store_dir=None) -> object:
        requests.append(request)
        _write_store_bars(
            ref,
            pd.DataFrame(
                {"Close": [5010.0, 5020.0, 5030.0]},
                index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
            ),
            store_dir=store_dir,
        )
        return object()

    monkeypatch.setattr(
        "aegis_data.coverage.pull_databento_futures_bars",
        pull_futures,
    )
    config = make_data_config(
        source="store",
        provider="databento",
        symbols=[
            {
                "root": "ES",
                "ccy": "USD",
                "dataset": "GLBX.MDP3",
                "adjustment": "unadjusted",
            }
        ],
        arrays=["Close"],
        start="2024-01-02",
        end="2024-01-05",
    )

    result = load_market_data_result(config)

    assert requests == [
        NativeBarsRequest(
            refs=(ref,),
            arrays=("Close",),
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            calendar=TradingCalendar.XNYS,
        )
    ]
    assert list(result.native_data.get(feature="Close").columns) == ["ES"]
    assert result.native_data.get(feature="Close")["ES"].tolist() == [5010.0, 5020.0, 5030.0]


def test_store_adapter_requests_each_mixed_dataset_futures_leg(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    pull = _RecordingMixedDatasetPull()
    monkeypatch.setattr("aegis_data.coverage.pull_databento_futures_bars", pull)

    load_market_data_result(_mixed_dataset_store_config())

    assert pull.requests == [
        NativeBarsRequest(
            refs=(_MIXED_SIGNAL_ES,),
            arrays=("Close",),
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            calendar=TradingCalendar.XNYS,
        ),
        NativeBarsRequest(
            refs=(_MIXED_SIGNAL_BZ,),
            arrays=("Close",),
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            calendar=TradingCalendar.XNYS,
        ),
        NativeBarsRequest(
            refs=(_MIXED_PNL_BZ,),
            arrays=("Close",),
            timeframe="1D",
            start="2024-01-02",
            end="2024-01-05",
            calendar=TradingCalendar.XNYS,
        ),
    ]


def test_store_adapter_loads_mixed_dataset_signal_and_pnl_series(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    pull = _RecordingMixedDatasetPull()
    monkeypatch.setattr("aegis_data.coverage.pull_databento_futures_bars", pull)

    result = load_market_data_result(_mixed_dataset_store_config())

    assert result.native_data.get(feature="Close")["ES"].tolist() == [1.0, 2.0, 3.0]
    assert result.native_data.get(feature="Close")["BZ"].tolist() == [10.0, 20.0, 30.0]
    assert result.pnl_native_data.get(feature="Close")["ES"].tolist() == [1.0, 2.0, 3.0]
    assert result.pnl_native_data.get(feature="Close")["BZ"].tolist() == [100.0, 200.0, 300.0]


def test_store_adapter_materializes_a_pnl_series_for_a_dual_adjustment_future(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])

    def pull_futures(request: NativeBarsRequest, *, store_dir=None) -> object:
        for ref in request.refs:
            close = [1.0, 2.0, 3.0] if ref.adjustment == "backward_ratio" else [10.0, 20.0, 30.0]
            _write_store_bars(
                ref,
                pd.DataFrame({"Close": close}, index=index),
                store_dir=store_dir,
            )
        return object()

    monkeypatch.setattr("aegis_data.coverage.pull_databento_futures_bars", pull_futures)
    config = make_data_config(
        source="store",
        provider="databento",
        symbols=[
            {
                "root": "ES",
                "ccy": "USD",
                "dataset": "GLBX.MDP3",
                "adjustment": "backward_ratio",
                "pnl_adjustment": "backward_spread",
            }
        ],
        arrays=["Close"],
        start="2024-01-02",
        end="2024-01-05",
    )

    result = load_market_data_result(config)

    # Signal series (indicators) is the backward_ratio adjustment.
    assert result.native_data.get(feature="Close")["ES"].tolist() == [1.0, 2.0, 3.0]
    # The P&L series (portfolio) is carried alongside as the backward_spread adjustment.
    assert result.pnl_native_data.get(feature="Close")["ES"].tolist() == [10.0, 20.0, 30.0]


def test_store_adapter_has_no_pnl_series_without_pnl_adjustment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))

    def pull_futures(request: NativeBarsRequest, *, store_dir=None) -> object:
        for ref in request.refs:
            _write_store_bars(
                ref,
                pd.DataFrame(
                    {"Close": [1.0, 2.0, 3.0]},
                    index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
                ),
                store_dir=store_dir,
            )
        return object()

    monkeypatch.setattr("aegis_data.coverage.pull_databento_futures_bars", pull_futures)
    config = make_data_config(
        source="store",
        provider="databento",
        symbols=[
            {
                "root": "ES",
                "ccy": "USD",
                "dataset": "GLBX.MDP3",
                "adjustment": "backward_ratio",
            }
        ],
        arrays=["Close"],
        start="2024-01-02",
        end="2024-01-05",
    )

    result = load_market_data_result(config)

    assert result.pnl_native_data is None


def test_store_fx_rates_pull_through_aegis_data_fx_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    requests: list[tuple[str, str, str]] = []

    def fetch_fx(locator: YFinanceLocator, request) -> pd.DataFrame:
        requests.append(
            (
                locator.ticker,
                pd.Timestamp(request.start).date().isoformat(),
                pd.Timestamp(request.end).date().isoformat(),
            )
        )
        return pd.DataFrame(
            {"Close": [1.10, 1.11, 1.12]},
            index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
        )

    monkeypatch.setattr("aegis_data.yfinance._fetch_yfinance", fetch_fx)
    config = make_data_config(
        source="store",
        provider="yfinance",
        symbols=[{"ticker": "SPY", "ccy": "USD", "figi": "BBG000B9XRY4"}],
        arrays=["Close"],
        start="2024-01-02",
        end="2024-01-05",
    )
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])

    rates = _load_fx_rates(config, base_currency="EUR", currencies={"USD"}, index=index)

    assert requests == [("EURUSD=X", "2024-01-02", "2024-01-05")]
    assert rates["USD"].tolist() == [1.10, 1.11, 1.12]


def test_remote_adapter_collapses_cross_venue_daily_indices_to_shared_dates() -> None:
    """The canonical case: ``.L`` (London) and ``.DE`` (Berlin) daily bars merge 1:1 by date.

    Each venue's daily bar arrives at LOCAL-exchange midnight in its own tz; aligning by
    UTC instant (vbt's default) would shift Berlin to the prior day and split every date
    into two rows -- a NaN checkerboard. The date collapse must land both venues on one
    UTC-midnight row per shared trade date. Exercises the real ``vbt.Data`` merge.
    """
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    close = _merge_cross_venue(
        [
            (_daily_venue_frame("Europe/London", dates, 0.0), {"freq": "1D"}),
            (_daily_venue_frame("Europe/Berlin", dates, 100.0), {"freq": "1D"}),
        ],
        ["VOD.L", "SAP.DE"],
        timeframe="1D",
        missing_index="drop",
    )

    assert list(close.columns) == ["VOD.L", "SAP.DE"]
    assert list(close.index.strftime("%Y-%m-%d")) == dates  # one row per shared date
    assert str(close.index.tz).upper() == "UTC"
    assert (close.index == close.index.normalize()).all()  # UTC midnight, not split instants
    assert int(close.isna().sum().sum()) == 0  # no checkerboard


def test_remote_adapter_realigns_cross_venue_intraday_onto_one_grid() -> None:
    """Intraday venues are distinct instants; the adapter realigns them onto one grid.

    ``09:30 Europe/London`` and ``09:30 Europe/Berlin`` are different moments, so a plain
    merge interleaves them as a NaN checkerboard. After the realign, the panel sits on a
    regular UTC grid at the source timeframe where each symbol carries its last-known
    value: NaN appears only as a leading warm-up block (no look-ahead, no interior holes),
    and both venues are populated once their sessions overlap. Exercises the real
    ``vbt.Data`` merge + realign (Open via realign_opening, Close via realign_closing).
    """
    stamps = ["2024-01-02 09:30", "2024-01-02 10:30", "2024-01-02 11:30"]
    london = pd.DataFrame(
        {"Open": [1.0, 2.0, 3.0], "Close": [1.5, 2.5, 3.5]},
        index=pd.DatetimeIndex(stamps).tz_localize("Europe/London"),
    )
    berlin = pd.DataFrame(
        {"Open": [4.0, 5.0, 6.0], "Close": [4.5, 5.5, 6.5]},
        index=pd.DatetimeIndex(stamps).tz_localize("Europe/Berlin"),
    )
    close = _merge_cross_venue(
        [(london, {"freq": "1h"}), (berlin, {"freq": "1h"})],
        ["VOD.L", "SAP.DE"],
        timeframe="1h",
        missing_index="raise",  # would explode on distinct instants but for the union override
        arrays=("Open", "Close"),
    )

    # Realigned onto a regular hourly UTC grid, not the interleaved raw instants.
    assert str(close.index.tz).upper() == "UTC"
    assert list(close.index.to_series().diff().dropna().unique()) == [pd.Timedelta("1h")]
    # No checkerboard: per symbol, NaN is only a leading warm-up prefix (no interior holes).
    for symbol in close.columns:
        valid = close[symbol].notna().to_numpy()
        assert valid[valid.argmax():].all()
    # Once both sessions overlap the panel is fully populated (carried forward, no look-ahead).
    assert close.iloc[-1].notna().all()


def _daily_venue_frame(tz: str, dates: list[str], base: float) -> pd.DataFrame:
    """A daily OHLC-less close panel at LOCAL-exchange midnight in ``tz``."""
    index = pd.DatetimeIndex([f"{d} 00:00:00" for d in dates]).tz_localize(tz)
    return pd.DataFrame({"Close": [base + i for i in range(len(dates))]}, index=index)


def _merge_cross_venue(
    raw_outputs,
    tickers,
    *,
    timeframe: str,
    missing_index: str,
    arrays: tuple[str, ...] = ("Close",),
) -> pd.DataFrame:
    """Drive the real ``vbt.Data`` merge through the adapter and return the Close panel."""
    config = make_data_config(
        source="yf",
        start="2024-01-01",
        end="2024-02-01",
        symbols=[{"ticker": t, "ccy": "USD"} for t in tickers],
        arrays=list(arrays),
        timeframe=timeframe,
        missing_index=missing_index,
    )
    merged = remote_adapter._native_from_remote_raw_outputs(
        vbt.Data, config, raw_outputs, wrapper_kwargs={}, provider_kwargs={}
    )
    return merged.close


def test_remote_adapter_daily_merge_keeps_local_date_for_far_from_utc_venue() -> None:
    """A daily bar denotes the venue's local calendar date, whatever its UTC offset.

    Tokyo's local midnight is the prior day in UTC, so aligning by instant would shift a
    ``.T`` bar back a day and de-align it from a ``.L`` bar on the same trade date. The
    date collapse must keep each venue on its own local date so they merge 1:1. Exercises
    the real ``vbt.Data`` merge (not a fake) across a 9-hour offset.
    """
    close = _merge_cross_venue(
        [
            (_daily_venue_frame("Asia/Tokyo", ["2024-01-04", "2024-01-05"], 1.0), {"freq": "1D"}),
            (_daily_venue_frame("Europe/London", ["2024-01-04", "2024-01-05"], 3.0), {"freq": "1D"}),
        ],
        ["7203.T", "VOD.L"],
        timeframe="1D",
        missing_index="drop",
    )

    assert list(close.index.strftime("%Y-%m-%d")) == ["2024-01-04", "2024-01-05"]
    assert int(close.isna().sum().sum()) == 0


def test_remote_adapter_daily_merge_handles_divergent_trading_calendars() -> None:
    """Venues with different holidays merge on shared dates; the policy decides the rest.

    London trades a day XETRA is closed. ``drop`` keeps the intersection (no NaN); ``nan``
    keeps the union with the closed venue NaN on exactly the divergent day -- the genuine
    calendar gap, not a timezone artifact.
    """
    raw = [
        (_daily_venue_frame("Europe/London", ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"], 0.0), {"freq": "1D"}),
        (_daily_venue_frame("Europe/Berlin", ["2024-01-02", "2024-01-03", "2024-01-05"], 100.0), {"freq": "1D"}),
    ]
    tickers = ["VOD.L", "SAP.DE"]

    dropped = _merge_cross_venue(
        [(f.copy(), kw) for f, kw in raw], tickers, timeframe="1D", missing_index="drop"
    )
    assert "2024-01-04" not in dropped.index.strftime("%Y-%m-%d").tolist()
    assert int(dropped.isna().sum().sum()) == 0

    unioned = _merge_cross_venue(
        [(f.copy(), kw) for f, kw in raw], tickers, timeframe="1D", missing_index="nan"
    )
    nan_dates = unioned.index[unioned["SAP.DE"].isna()].strftime("%Y-%m-%d").tolist()
    assert nan_dates == ["2024-01-04"]


def test_remote_adapter_chains_original_pull_failure_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_REMOTE_API_KEY", "super-secret-token")
    config = make_data_config(
        source="fakeremote",
        symbols=[{"ticker": "SYN", "ccy": "EUR"}],
        arrays=["Close"],
        provider_kwargs={"api_key": {"env": "FAKE_REMOTE_API_KEY"}},
    )

    with pytest.raises(RemoteDataPullError) as error:
        remote_adapter.load_vbt_remote_source("fakeremote", _ExplodingRemoteData, config)

    assert "super-secret-token" in str(error.value)
    assert "<redacted>" not in str(error.value)
    assert isinstance(error.value.__cause__, RuntimeError)
    assert "super-secret-token" in str(error.value.__cause__)


class _ExplodingRemoteData:
    @classmethod
    def pull(cls, symbols, *, api_key=None, **kwargs):
        raise RuntimeError(f"auth rejected for key {api_key}")


class _LeakyProviderData:
    """A native object that would leak a secret if describe reached into it."""

    index = pd.date_range("2020-01-01", periods=3, freq="1D", tz="UTC")
    features = ("Close",)
    symbols = ("SYN",)
    fetch_kwargs: ClassVar[dict[str, object]] = {"period": "1mo", "api_key": "super-secret-token"}

    def get(self, feature=None, **_kwargs) -> pd.DataFrame:
        if feature not in {None, "Close"}:
            raise ValueError(feature)
        return pd.DataFrame({"SYN": [1.0, 2.0, 3.0]}, index=self.index)


class _FakeRemoteData:
    """A remote VBT-shaped data class whose native object retains unsafe mappings."""

    index = pd.date_range("2020-01-01", periods=3, freq="1D", tz="UTC")
    symbols = ("SYN",)
    features = ("Close",)
    fetch_kwargs: ClassVar[dict[str, object]] = {
        "period": "1mo",
        "limit": 100,
        "headers": {"period": "sessionid=abc"},
        "cache_path": "/home/alice/cache.db",
    }
    returned_kwargs: ClassVar[dict[str, object]] = {"freq": "1D", "auth": {"tz": "UTC"}}

    @classmethod
    def pull(cls, symbols, **kwargs):
        index = pd.date_range("2020-01-01", periods=3, freq="1D", tz="UTC", name="Open time")
        frame = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=index)
        return [(frame.copy(), {"freq": "1D"}) for _symbol in symbols]

    @classmethod
    def from_data(cls, data, **_kwargs):
        return cls()

    def get(self, feature=None, **_kwargs) -> pd.DataFrame:
        if feature not in {None, "Close"}:
            raise ValueError(feature)
        return pd.DataFrame({"SYN": [1.0, 2.0, 3.0]}, index=self.index)
