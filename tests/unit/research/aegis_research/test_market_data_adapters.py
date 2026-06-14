from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.data import load_market_data_result
from research.aegis_research.market_data.adapters import csv as csv_adapter
from research.aegis_research.market_data.adapters import remote as remote_adapter
from research.aegis_research.market_data.adapters import synthetic as synthetic_adapter
from research.aegis_research.market_data.contracts import (
    MarketDataAdapterResult,
    RemoteDataPullError,
)
from tests.support.research.aegis_research.factories import make_data_config


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
