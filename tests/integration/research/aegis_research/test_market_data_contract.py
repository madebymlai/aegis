from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from research.aegis_research import data as data_module
from research.aegis_research.config import DataConfig, LabelConfig, LabelGeneratorConfig
from research.aegis_research.data import (
    MarketDataAdapterResult,
    close_from_ohlcv,
    load_market_data_result,
    required_ohlcv_features,
)


def test_synthetic_result_exposes_native_data_quality_and_diagnostics() -> None:
    result = load_market_data_result(DataConfig(rows=10, symbols=["AAA", "BBB"]))

    assert result.native_data.feature_oriented
    assert result.quality.state == "healthy"
    assert {row["symbol"] for row in result.diagnostics} == {"AAA", "BBB"}
    assert result.metadata["quality"]["state"] == "healthy"
    assert close_from_ohlcv(result).shape == (10, 2)


def test_csv_feature_map_wraps_non_standard_flat_columns(tmp_path: Path) -> None:
    path = tmp_path / "prices.csv"
    index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="time")
    frame = pd.DataFrame(
        {
            "my_open": [1.0, 2.0, 3.0],
            "my_close": [1.5, 2.5, 3.5],
        },
        index=index,
    )
    frame.to_csv(path)

    result = load_market_data_result(
        DataConfig(
            source="csv",
            path=str(path),
            symbols=["SYN"],
            feature_map={"open": "my_open", "close": "my_close"},
        )
    )

    assert result.quality.state == "healthy"
    assert list(result.feature("Close").columns) == ["SYN"]
    assert result.metadata["ohlc_available"]["Close"] is True
    assert str(path) not in json.dumps(result.metadata)


def test_csv_multiindex_symbol_feature_layout_preserves_symbols(tmp_path: Path) -> None:
    path = tmp_path / "multi.csv"
    index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="time")
    frame = pd.DataFrame(
        {
            ("AAA", "Close"): [1.0, 2.0, 3.0],
            ("BBB", "Close"): [4.0, 5.0, 6.0],
            ("AAA", "High"): [1.1, 2.1, 3.1],
            ("BBB", "High"): [4.1, 5.1, 6.1],
        },
        index=index,
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=["symbol", "feature"])
    frame.to_csv(path)

    result = load_market_data_result(
        DataConfig(source="csv", path=str(path), symbols=["AAA", "BBB"])
    )

    assert result.quality.state == "healthy"
    assert list(result.feature("Close").columns) == ["AAA", "BBB"]


def test_csv_multiindex_layout_uses_one_full_pandas_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "multi.csv"
    index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="time")
    frame = pd.DataFrame(
        {
            ("AAA", "Close"): [1.0, 2.0, 3.0],
            ("BBB", "Close"): [4.0, 5.0, 6.0],
        },
        index=index,
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=["symbol", "feature"])
    frame.to_csv(path)
    read_headers = []
    read_csv = data_module.pd.read_csv

    def spy_read_csv(*args, **kwargs):
        read_headers.append(kwargs.get("header"))
        return read_csv(*args, **kwargs)

    monkeypatch.setattr(data_module.pd, "read_csv", spy_read_csv)

    result = load_market_data_result(
        DataConfig(source="csv", path=str(path), symbols=["AAA", "BBB"])
    )

    assert result.quality.state == "healthy"
    assert read_headers == [[0, 1]]


def test_missing_required_feature_marks_quality_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing_close.csv"
    frame = pd.DataFrame(
        {"High": [1.0, 2.0, 3.0]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(DataConfig(source="csv", path=str(path), symbols=["SYN"]))

    assert result.quality.state == "rejected"
    assert "required feature 'Close' is unavailable" in result.quality.reasons


def test_non_numeric_required_feature_marks_quality_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_close.csv"
    frame = pd.DataFrame(
        {"Close": ["a", "b", "c"]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(DataConfig(source="csv", path=str(path), symbols=["SYN"]))

    assert result.quality.state == "rejected"
    assert "required feature 'Close' has non-numeric symbols ['SYN']" in result.quality.reasons


def test_future_provider_adapter_uses_same_result_contract() -> None:
    native_data = load_market_data_result(DataConfig(rows=5, symbols=["FUT"])).native_data

    result = load_market_data_result(
        DataConfig(source="future", symbols=["FUT"]),
        adapters={"future": lambda _config: MarketDataAdapterResult(native_data=native_data)},
    )

    assert result.quality.state == "healthy"
    assert result.feature("Close").shape == (5, 1)


def test_required_features_follow_label_kind() -> None:
    assert required_ohlcv_features("fixlb") == ("Close",)
    assert required_ohlcv_features("trendlb") == ("Close", "High", "Low")
    assert required_ohlcv_features("pivotlb") == ("Close", "High", "Low")
    assert required_ohlcv_features(LabelConfig()) == ("Close",)
    assert required_ohlcv_features(LabelConfig(generator=LabelGeneratorConfig(kind="trendlb"))) == (
        "Close",
        "High",
        "Low",
    )
