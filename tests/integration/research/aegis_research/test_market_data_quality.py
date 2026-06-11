from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pandas as pd

from research.aegis_research.configuration import DataConfig
from research.aegis_research.data import (
    DataDiagnostics,
    DataArrayDiagnostics,
    MarketDataAdapterResult,
    RemoteDataPullError,
    load_market_data_result,
    required_experiment_ohlcv_arrays,
)
from research.aegis_research.market_data import quality as data_quality
from tests.support.research.aegis_research.factories import (
    make_data_config,
    make_data_quality_config,
    make_signal_config,
)


def test_quality_verdict_is_derived_from_typed_diagnostics_without_panels() -> None:
    quality = data_quality.evaluate(
        make_data_config(source="diagnostic", symbols=["SYN"], arrays=["Close"]),
        (
            DataDiagnostics(
                symbol="SYN",
                configured=True,
                arrays={
                    "Close": DataArrayDiagnostics(
                        available=True,
                        rows=3,
                        missing=1,
                        numeric=False,
                    )
                },
                index_evidence={
                    "raw_index_has_duplicates": True,
                    "raw_index_monotonic_increasing": False,
                },
            ),
        ),
        required_arrays=("Close",),
    )

    assert quality.state == "rejected"
    assert quality.reasons == (
        "raw data index contains duplicate timestamps",
        "raw data index is not monotonic increasing",
        "required feature 'Close' contains missing values",
        "required feature 'Close' has non-numeric symbols ['SYN']",
    )


def test_duplicate_csv_index_is_rejected_before_vectorbt_normalizes(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.csv"
    frame = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.to_datetime(["2020-01-01", "2020-01-01", "2020-01-02"], utc=True),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        make_data_config(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"])
    )

    assert result.quality.state == "rejected"
    assert "raw data index contains duplicate timestamps" in result.quality.reasons
    assert result.metadata.provenance.index_evidence["raw_index_has_duplicates"] is True


def test_non_monotonic_csv_index_is_rejected_before_vectorbt_sorts(tmp_path: Path) -> None:
    path = tmp_path / "non_monotonic.csv"
    frame = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.to_datetime(["2020-01-02", "2020-01-01", "2020-01-03"], utc=True),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        make_data_config(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"])
    )

    assert result.quality.state == "rejected"
    assert "raw data index is not monotonic increasing" in result.quality.reasons


def test_missing_required_rows_are_rejected_by_default(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    frame = pd.DataFrame(
        {"Close": [1.0, None, 3.0]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        make_data_config(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"])
    )

    assert result.quality.state == "rejected"
    assert "required feature 'Close' contains missing values" in result.quality.reasons


def test_allowed_missing_rows_are_degraded_allowed(tmp_path: Path) -> None:
    path = tmp_path / "allowed_missing.csv"
    frame = pd.DataFrame(
        {"Close": [1.0, None, 3.0]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        make_data_config(
            source="csv",
            path=str(path),
            symbols=["SYN"],
            arrays=["Close"],
            quality=make_data_quality_config(allowed_degradations=["missing_rows"]),
        )
    )

    assert result.quality.state == "degraded_allowed"
    assert "required feature 'Close' contains missing values" in result.quality.warnings


def test_close_only_array_does_not_require_unconfigured_ohlcv_arrays(tmp_path: Path) -> None:
    path = tmp_path / "close_only.csv"
    frame = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        make_data_config(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"])
    )

    assert result.quality.state == "healthy"
    assert result.quality.warnings == ()


def test_next_open_signal_timing_requires_open_feature() -> None:
    assert required_experiment_ohlcv_arrays() == ("Close", "Open")
    assert required_experiment_ohlcv_arrays(signal_config=make_signal_config()) == ("Close", "Open")


def test_same_close_signal_timing_does_not_require_open_feature() -> None:
    assert required_experiment_ohlcv_arrays(
        signal_config=make_signal_config(execution_timing="same_close")
    ) == ("Close",)


def test_next_open_feature_requirement_rejects_close_only_data(tmp_path: Path) -> None:
    path = tmp_path / "close_only.csv"
    frame = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        make_data_config(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"]),
        required_arrays=required_experiment_ohlcv_arrays(signal_config=make_signal_config()),
    )

    assert result.quality.state == "rejected"
    assert "required feature 'Open' is unavailable" in result.quality.reasons


def test_same_close_feature_requirement_allows_close_only_data(tmp_path: Path) -> None:
    path = tmp_path / "close_only.csv"
    frame = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        make_data_config(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"]),
        required_arrays=required_experiment_ohlcv_arrays(
            signal_config=make_signal_config(execution_timing="same_close")
        ),
    )

    assert result.quality.state == "healthy"


def test_explicit_high_low_requirement_rejects_close_only_data(tmp_path: Path) -> None:
    path = tmp_path / "close_only.csv"
    frame = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        make_data_config(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"]),
        required_arrays=("Close", "High", "Low"),
    )

    assert result.quality.state == "rejected"
    assert "required feature 'High' is unavailable" in result.quality.reasons
    assert "required feature 'Low' is unavailable" in result.quality.reasons


def test_skipped_symbol_requires_skip_policy_opt_in() -> None:
    native_data = load_market_data_result(make_data_config(rows=5, symbols=["AAA"])).native_data

    result = load_market_data_result(
        make_data_config(source="fake", symbols=["AAA", "BBB"]),
        adapters={"fake": lambda _config: MarketDataAdapterResult(native_data=native_data)},
    )

    assert result.quality.state == "rejected"
    assert "configured symbols missing from loaded data: ['BBB']" in result.quality.reasons


def test_skipped_symbol_with_explicit_policy_is_degraded_allowed() -> None:
    native_data = load_market_data_result(make_data_config(rows=5, symbols=["AAA"])).native_data

    result = load_market_data_result(
        make_data_config(
            source="fake",
            symbols=["AAA", "BBB"],
            skip_on_error=True,
            quality=make_data_quality_config(allowed_degradations=["skipped_symbols"]),
        ),
        adapters={"fake": lambda _config: MarketDataAdapterResult(native_data=native_data)},
    )

    assert result.quality.state == "degraded_allowed"
    assert "configured symbols missing from loaded data: ['BBB']" in result.quality.warnings


def test_remote_post_alignment_evidence_is_explicit() -> None:
    native_data = load_market_data_result(make_data_config(rows=5, symbols=["AAA"])).native_data

    result = load_market_data_result(
        make_data_config(source="fake", symbols=["AAA"]),
        adapters={
            "fake": lambda _config: MarketDataAdapterResult(
                native_data=native_data,
                evidence={"source": "post_vectorbt_alignment"},
            )
        },
    )

    assert result.metadata.provenance.index_evidence["source"] == "post_vectorbt_alignment"


def test_provider_failure_returns_safe_non_usable_result() -> None:
    def fail(_config: DataConfig) -> MarketDataAdapterResult:
        raise RemoteDataPullError("fake", "network unavailable")

    result = load_market_data_result(
        make_data_config(source="fake", symbols=["AAA"]),
        adapters={"fake": fail},
    )

    assert result.native_data is None
    assert result.quality.state == "provider_failed"
    assert result.metadata.quality["state"] == "provider_failed"
    assert result.metadata.diagnostics[0]["provider_status"] == "provider_failed"
    assert "network unavailable" not in str(result.metadata)


def test_provider_update_support_uses_symbol_update_capability() -> None:
    result = load_market_data_result(
        make_data_config(source="fake", symbols=["SYN"]),
        adapters={
            "fake": lambda _config: MarketDataAdapterResult(
                native_data=_UpdateCapableProviderData()
            )
        },
    )

    assert result.metadata.provenance.update_supported is True


def test_provider_update_support_uses_feature_update_capability() -> None:
    result = load_market_data_result(
        make_data_config(source="fake", symbols=["SYN"]),
        adapters={
            "fake": lambda _config: MarketDataAdapterResult(
                native_data=_FeatureUpdateProviderData()
            )
        },
    )

    assert result.metadata.provenance.update_supported is True


class _ProviderMetadataData:
    index = pd.date_range("2020-01-01", periods=3, freq="1D", tz="UTC")
    features: ClassVar[list[str]] = ["Close"]
    symbols: ClassVar[list[str]] = ["SYN"]
    fetch_kwargs: ClassVar[dict[str, object]] = {
        "period": "1mo",
        "limit": 100,
        "headers": {"period": "sessionid=abc"},
        "cache_path": "/home/alice/cache.db",
    }
    returned_kwargs: ClassVar[dict[str, object]] = {"freq": "1D", "auth": {"tz": "UTC"}}

    def get(self, feature=None, **_kwargs) -> pd.DataFrame:
        if feature not in {None, "Close"}:
            raise ValueError(feature)
        return pd.DataFrame({"SYN": [1.0, 2.0, 3.0]}, index=self.index)


class _UpdateCapableProviderData(_ProviderMetadataData):
    symbol_oriented = True

    def update_symbol(self, symbol: str, **_kwargs) -> pd.DataFrame:
        return pd.DataFrame({symbol: [4.0]}, index=self.index[:1])


class _FeatureUpdateProviderData(_ProviderMetadataData):
    feature_oriented = True

    def update_feature(self, feature: str, **_kwargs) -> pd.DataFrame:
        return pd.DataFrame({"SYN": [4.0]}, index=self.index[:1])
