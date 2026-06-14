from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pandas as pd
import pytest

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
    """Different-tz daily bars (.L vs .DE) must merge on calendar date, not UTC instant.

    Yahoo returns each venue's daily bar at LOCAL-exchange midnight, labelled in the
    exchange tz. Aligning by UTC instant (vbt's default) shifts non-UTC venues to the
    prior day at a venue-specific hour, so no two venues ever share an index row -- a
    full NaN checkerboard. The remote adapter must first collapse each daily index to
    its calendar date so ``from_data`` merges the venues cleanly.

    Regression for the cross-exchange daily merge (commit 83bc13c): the prior fake
    returned one shared index for every symbol, so the multi-timezone merge -- the
    whole point of the alignment -- went unexercised.
    """
    days = pd.bdate_range("2024-01-02", "2024-01-10")
    london = pd.DataFrame(
        {"Close": range(len(days))},
        index=pd.DatetimeIndex([f"{d.date()} 00:00:00" for d in days]).tz_localize(
            "Europe/London"
        ),
    )
    berlin = pd.DataFrame(
        {"Close": range(len(days))},
        index=pd.DatetimeIndex([f"{d.date()} 00:00:00" for d in days]).tz_localize(
            "Europe/Berlin"
        ),
    )
    raw_outputs = [(london, {"freq": "1D"}), (berlin, {"freq": "1D"})]
    config = make_data_config(
        source="fakeremote",
        symbols=[{"ticker": "VOD.L", "ccy": "GBP"}, {"ticker": "SAP.DE", "ccy": "EUR"}],
        arrays=["Close"],
        timeframe="1D",
    )
    captured: dict[str, pd.DataFrame] = {}

    class _CapturingRemoteData:
        @classmethod
        def from_data(cls, data, **_kwargs):
            captured.update(data)
            return cls()

    remote_adapter._native_from_remote_raw_outputs(
        _CapturingRemoteData, config, raw_outputs, wrapper_kwargs={}, provider_kwargs={}
    )

    london_idx = captured["VOD.L"].index
    berlin_idx = captured["SAP.DE"].index
    # Collapsed to tz-naive calendar dates (a daily bar denotes a date, not an instant)...
    assert london_idx.tz is None and berlin_idx.tz is None
    assert (london_idx == london_idx.normalize()).all()
    # ...so the two venues carry identical labels and merge 1:1. Under the UTC-instant
    # default these would be all-distinct -- the NaN-checkerboard "pollution".
    assert london_idx.equals(berlin_idx)


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
