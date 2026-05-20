from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pandas as pd
import pytest

from research.aegis_research import data as data_module
from research.aegis_research.config import DataConfig
from research.aegis_research.data import (
    LOGICAL_FEATURES,
    OHLCV_FEATURES,
    QUALITY_HEALTHY,
    REMOTE_DATA_CLASSES,
    MarketDataAdapterResult,
    MarketDataBundle,
    RemoteDataPullError,
    close_from_ohlcv,
    load_market_data_result,
    market_data_bundle,
    required_ohlcv_features,
)
from research.aegis_research.labels import LabelConfig, LabelGeneratorConfig
from research.aegis_research.market_data.sources import vbt_data_source_classes


def test_synthetic_result_exposes_native_data_quality_and_diagnostics() -> None:
    result = load_market_data_result(DataConfig(rows=10, symbols=["AAA", "BBB"]))
    bundle = market_data_bundle(result)

    assert result.native_data.feature_oriented
    assert result.quality.state == "healthy"
    assert {row["symbol"] for row in result.diagnostics} == {"AAA", "BBB"}
    assert result.metadata["quality"]["state"] == "healthy"
    assert close_from_ohlcv(result).shape == (10, 2)
    assert bundle.feature("Close").equals(result.feature("Close"))


def test_market_data_bundle_can_resolve_named_features() -> None:
    index = pd.date_range("2020-01-01", periods=2, tz="UTC")
    close = pd.DataFrame({"SYN": [1.0, 2.0]}, index=index)
    factor = pd.DataFrame({"SYN": [10.0, 20.0]}, index=index)
    bundle = MarketDataBundle(
        features={"Close": close},
        loaded_features=("Close", "Factor"),
        feature_getter=lambda feature: factor,
    )

    assert bundle.feature("Factor").equals(factor)


def test_market_data_bundle_rejects_unloaded_features() -> None:
    index = pd.date_range("2020-01-01", periods=2, tz="UTC")
    close = pd.DataFrame({"SYN": [1.0, 2.0]}, index=index)
    bundle = MarketDataBundle(
        features={"Close": close},
        loaded_features=("Close",),
        feature_getter=lambda feature: close,
    )

    with pytest.raises(ValueError, match="was not loaded"):
        bundle.feature("FundingRate")


def test_data_facade_preserves_public_market_data_constants() -> None:
    assert OHLCV_FEATURES == ("Open", "High", "Low", "Close", "Volume")
    assert LOGICAL_FEATURES["close"] == "Close"
    assert QUALITY_HEALTHY == "healthy"
    assert "yf" in REMOTE_DATA_CLASSES


def test_dynamic_vbt_source_discovery_uses_current_vbt_classes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(data_module.vbt, "DemoData", _DemoRemoteData, raising=False)
    monkeypatch.setattr(data_module.vbt, "DemoNoPullData", object, raising=False)

    source_classes = vbt_data_source_classes()
    result = load_market_data_result(
        DataConfig(
            source="demo",
            symbols=["SYN"],
            start="2020-01-01",
            end="2020-01-03",
            timeframe="1D",
        )
    )

    assert source_classes["demo"] is _DemoRemoteData
    assert "demonopull" not in source_classes
    assert result.quality.state == "healthy"
    assert result.metadata["source"] == "demo"


def test_provider_shaped_source_loads_dynamic_feature_arrays() -> None:
    native_data = _DemoRemoteData(["SYN"], features=["Close", "FundingRate"])

    result = load_market_data_result(
        DataConfig(source="future", symbols=["SYN"], arrays=["Close", "FundingRate"]),
        adapters={"future": lambda _config: MarketDataAdapterResult(native_data=native_data)},
    )
    bundle = market_data_bundle(result)

    assert result.quality.state == "healthy"
    assert result.metadata["loaded_arrays"] == ["Close", "FundingRate"]
    assert result.feature("FundingRate").iloc[-1, 0] == 0.03
    assert bundle.feature("FundingRate").equals(result.feature("FundingRate"))


def test_remote_source_projects_configured_arrays_before_column_alignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(data_module.vbt, "ProviderExtrasData", _ProviderExtrasData, raising=False)

    result = load_market_data_result(
        DataConfig(
            source="providerextras",
            symbols=["AAA", "BBB"],
            arrays=["OHLCV"],
            start="2020-01-01",
            end="2020-01-03",
            timeframe="1D",
            missing_columns="raise",
        )
    )

    assert _ProviderExtrasData.last_pull_kwargs["return_raw"] is True
    assert _ProviderExtrasData.from_data_columns == {
        "AAA": ["Open", "High", "Low", "Close", "Volume"],
        "BBB": ["Open", "High", "Low", "Close", "Volume"],
    }
    assert _ProviderExtrasData.last_from_data_kwargs["missing_columns"] == "raise"
    assert result.quality.state == "healthy"
    assert result.metadata["loaded_arrays"] == ["Open", "High", "Low", "Close", "Volume"]


def test_bundle_can_serve_dynamic_feature_without_close() -> None:
    native_data = _DemoRemoteData(["SYN"], features=["FundingRate"])

    result = load_market_data_result(
        DataConfig(source="future", symbols=["SYN"], arrays=["FundingRate"]),
        adapters={"future": lambda _config: MarketDataAdapterResult(native_data=native_data)},
    )
    bundle = market_data_bundle(result)

    with pytest.raises(ValueError, match="was not loaded"):
        bundle.feature("Close")
    assert bundle.feature("FundingRate").iloc[-1, 0] == 0.03


def test_provider_failure_metadata_preserves_required_arrays() -> None:
    def fail(_config: DataConfig) -> MarketDataAdapterResult:
        raise RemoteDataPullError("future", "network unavailable")

    result = load_market_data_result(
        DataConfig(source="future", symbols=["SYN"], arrays=["Close"]),
        required_features=("OpenInterest",),
        adapters={"future": fail},
    )

    assert result.quality.state == "provider_failed"
    assert result.metadata["required_arrays"] == ["Close", "OpenInterest"]
    assert result.metadata["unavailable_arrays"] == ["Close", "OpenInterest"]


def test_csv_flat_vbt_feature_names_load_without_mapping(tmp_path: Path) -> None:
    path = tmp_path / "prices.csv"
    index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="time")
    frame = pd.DataFrame(
        {
            "Open": [1.0, 2.0, 3.0],
            "Close": [1.5, 2.5, 3.5],
        },
        index=index,
    )
    frame.to_csv(path)

    result = load_market_data_result(
        DataConfig(
            source="csv",
            path=str(path),
            symbols=["SYN"],
            arrays=["Open", "Close"],
        )
    )

    assert result.quality.state == "healthy"
    assert list(result.feature("Close").columns) == ["SYN"]
    assert result.metadata["ohlc_available"]["Close"] is True
    assert str(path) not in json.dumps(result.metadata)


def test_csv_non_standard_flat_columns_fail_without_mapping(tmp_path: Path) -> None:
    path = tmp_path / "prices.csv"
    frame = pd.DataFrame(
        {"my_close": [1.0, 2.0, 3.0]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        DataConfig(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"])
    )

    assert result.quality.state == "rejected"
    assert "required feature 'Close' is unavailable" in result.quality.reasons


def test_csv_extra_vbt_feature_loads_through_dynamic_access(tmp_path: Path) -> None:
    path = tmp_path / "funding.csv"
    frame = pd.DataFrame(
        {
            "Close": [1.0, 2.0, 3.0],
            "FundingRate": [0.01, 0.02, 0.03],
        },
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        DataConfig(source="csv", path=str(path), symbols=["SYN"], arrays=["Close", "FundingRate"])
    )

    assert result.quality.state == "healthy"
    assert result.feature("FundingRate").iloc[-1, 0] == 0.03
    assert result.metadata["loaded_arrays"] == ["Close", "FundingRate"]


def test_configured_unused_array_must_still_load(tmp_path: Path) -> None:
    path = tmp_path / "missing_funding.csv"
    frame = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        DataConfig(source="csv", path=str(path), symbols=["SYN"], arrays=["Close", "FundingRate"])
    )

    assert result.quality.state == "rejected"
    assert "required feature 'FundingRate' is unavailable" in result.quality.reasons
    assert result.metadata["unavailable_arrays"] == ["FundingRate"]


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
        DataConfig(source="csv", path=str(path), symbols=["AAA", "BBB"], arrays=["Close", "High"])
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
        DataConfig(source="csv", path=str(path), symbols=["AAA", "BBB"], arrays=["Close"])
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

    result = load_market_data_result(
        DataConfig(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"])
    )

    assert result.quality.state == "rejected"
    assert "required feature 'Close' is unavailable" in result.quality.reasons


def test_non_numeric_required_feature_marks_quality_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_close.csv"
    frame = pd.DataFrame(
        {"Close": ["a", "b", "c"]},
        index=pd.date_range("2020-01-01", periods=3, tz="UTC"),
    )
    frame.to_csv(path)

    result = load_market_data_result(
        DataConfig(source="csv", path=str(path), symbols=["SYN"], arrays=["Close"])
    )

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


class _DemoRemoteData:
    def __init__(self, symbols: list[str], *, features: list[str] | None = None) -> None:
        self.symbols = symbols
        self.index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="Open time")
        self.features = features or ["Open", "High", "Low", "Close", "Volume"]

    @classmethod
    def pull(cls, symbols, **kwargs):
        if kwargs.get("return_raw"):
            index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="Open time")
            frame = pd.DataFrame(
                {
                    "Open": [1.0, 2.0, 3.0],
                    "High": [1.1, 2.1, 3.1],
                    "Low": [0.9, 1.9, 2.9],
                    "Close": [1.0, 2.0, 3.0],
                    "Volume": [100.0, 100.0, 100.0],
                },
                index=index,
            )
            return [(frame.copy(), {"tz": "UTC", "freq": "1D"}) for _symbol in symbols]
        return cls(list(symbols))

    @classmethod
    def from_data(cls, data, **_kwargs):
        return cls(list(data), features=list(next(iter(data.values())).columns))

    def get(self, feature=None, **_kwargs) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "Open": [1.0, 2.0, 3.0],
                "High": [1.1, 2.1, 3.1],
                "Low": [0.9, 1.9, 2.9],
                "Close": [1.0, 2.0, 3.0],
                "Volume": [100.0, 100.0, 100.0],
                "FundingRate": [0.01, 0.02, 0.03],
            },
            index=self.index,
        )
        frame = frame.loc[:, self.features]
        frame.columns = pd.MultiIndex.from_product(
            [self.symbols, frame.columns], names=["symbol", "feature"]
        )
        if feature is None:
            return frame
        return frame.xs(feature, axis=1, level="feature")


class _ProviderExtrasData:
    last_pull_kwargs: ClassVar[dict[str, object]] = {}
    last_from_data_kwargs: ClassVar[dict[str, object]] = {}
    from_data_columns: ClassVar[dict[str, list[str]]] = {}

    def __init__(self, data: dict[str, pd.DataFrame]) -> None:
        self.data = data
        self.symbols = list(data)
        self.index = next(iter(data.values())).index
        self.features = list(next(iter(data.values())).columns)

    @classmethod
    def pull(cls, symbols, **kwargs):
        cls.last_pull_kwargs = dict(kwargs)
        if kwargs.get("return_raw") is not True:
            raise ValueError("Symbols have mismatching columns")
        index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="Open time")
        outputs = []
        for symbol in symbols:
            extra_feature = "Dividends" if symbol == "AAA" else "Capital Gains"
            columns = ["Open", "High", "Low", "Close", "Volume", extra_feature]
            frame = pd.DataFrame(
                {column: [1.0, 2.0, 3.0] for column in columns},
                index=index,
            )
            outputs.append((frame, {"tz": "UTC", "freq": "1D"}))
        return outputs

    @classmethod
    def from_data(cls, data, **kwargs):
        cls.last_from_data_kwargs = dict(kwargs)
        cls.from_data_columns = {
            symbol: list(frame.columns) for symbol, frame in data.items()
        }
        return cls(data)

    def get(self, feature=None, **_kwargs) -> pd.DataFrame:
        if feature is None:
            frames = []
            for symbol, frame in self.data.items():
                symbol_frame = frame.copy()
                symbol_frame.columns = pd.MultiIndex.from_product(
                    [[symbol], symbol_frame.columns], names=["symbol", "feature"]
                )
                frames.append(symbol_frame)
            return pd.concat(frames, axis=1)
        if feature not in self.features:
            raise ValueError(feature)
        return pd.DataFrame(
            {symbol: frame[feature] for symbol, frame in self.data.items()},
            index=self.index,
        )
