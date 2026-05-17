from __future__ import annotations

import inspect

import pandas as pd

from research.aegis_research import experiments
from research.aegis_research.config import (
    DataConfig,
    IndicatorConfig,
    LabelConfig,
    SplitConfig,
)
from research.aegis_research.data import close_from_ohlcv, load_market_data_result
from research.aegis_research.data_schema import ohlc_availability
from research.aegis_research.indicators import build_indicator_result
from research.aegis_research.labels import build_label_result
from research.aegis_research.splits import build_validation_splits_result


def test_experiments_no_longer_imports_private_label_primary_close() -> None:
    source = inspect.getsource(experiments)

    assert "from research.aegis_research.labels import _primary_close" not in source
    assert "_primary_close(" not in source


def test_data_schema_reports_ohlc_availability() -> None:
    index = pd.date_range("2020-01-01", periods=3, tz="UTC")
    data = pd.DataFrame(
        {
            ("AAA", "Close"): [1.0, 2.0, 3.0],
            ("BBB", "Close"): [4.0, 5.0, 6.0],
            ("AAA", "High"): [1.1, 2.1, 3.1],
        },
        index=index,
    )
    data.columns = pd.MultiIndex.from_tuples(data.columns, names=["symbol", "feature"])

    assert ohlc_availability(data) == {"Close": True, "High": True, "Low": False, "Open": False}


def test_data_stage_result_exposes_metadata_without_recorder_ids() -> None:
    result = load_market_data_result(DataConfig(rows=10, symbols=["SYN"]))

    assert result.native_data.feature_oriented
    assert close_from_ohlcv(result.native_data).shape == (10, 1)
    assert result.metadata["source"] == "synthetic"
    assert result.metadata["shape"]["rows"] == 10
    assert "artifact_id" not in result.metadata


def test_indicator_and_label_results_expose_portable_metadata() -> None:
    data = load_market_data_result(DataConfig(rows=120, symbols=["SYN"])).native_data
    close = close_from_ohlcv(data)

    indicators = build_indicator_result(close, IndicatorConfig())
    labels = build_label_result(close, LabelConfig())

    assert indicators.frame.shape[0] == 120
    assert indicators.metadata["specs"][0]["id"] == "returns"
    assert indicators.metadata["specs"][0]["parameter_combinations"] == [
        {"window": 1},
        {"window": 5},
        {"window": 20},
    ]
    assert indicators.native_objects["ma"] is not None
    assert indicators.lineage[0]["symbol"] == "SYN"
    assert list(labels.labels.columns) == ["SYN"]
    assert labels.metadata["kind"] == "fixlb"
    assert labels.native_object is not None


def test_split_result_exposes_holdout_and_rolling_metadata() -> None:
    index = pd.date_range("2020-01-01", periods=120, tz="UTC")

    holdout = build_validation_splits_result(index, SplitConfig(kind="holdout"))
    rolling = build_validation_splits_result(index, SplitConfig(kind="rolling", n=3, length=40))

    assert holdout.metadata["kind"] == "holdout"
    assert holdout.metadata["n_splits"] == 1
    assert rolling.metadata["kind"] == "rolling"
    assert rolling.metadata["n_splits"] == 3
    assert rolling.native_object is not None
