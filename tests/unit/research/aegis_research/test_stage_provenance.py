from __future__ import annotations

import pandas as pd

from research.aegis_research.config import DataConfig
from research.aegis_research.data import close_from_ohlcv, load_market_data_result
from research.aegis_research.data_schema import ohlc_availability


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
