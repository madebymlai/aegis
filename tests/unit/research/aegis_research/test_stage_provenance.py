from __future__ import annotations

from research.aegis_research.data import close_from_ohlcv, load_market_data_result
from tests.support.research.aegis_research.factories import make_data_config


def test_data_stage_result_exposes_metadata_without_recorder_ids() -> None:
    result = load_market_data_result(make_data_config(rows=10, symbols=["SYN"]))

    assert result.native_data.feature_oriented
    assert close_from_ohlcv(result.native_data).shape == (10, 1)
    assert result.metadata["source"] == "synthetic"
    assert result.metadata["shape"]["rows"] == 10
    assert "artifact_id" not in result.metadata
