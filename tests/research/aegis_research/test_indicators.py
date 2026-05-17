from __future__ import annotations

import pandas as pd
import pytest

from research.aegis_research import indicators as indicators_module
from research.aegis_research.config import (
    IndicatorConfig,
    IndicatorFeatureConfig,
    IndicatorSpecConfig,
    ModelConfig,
)
from research.aegis_research.indicator_registry import IndicatorDefinition
from research.aegis_research.indicators import build_indicator_result, build_model_feature_matrix
from research.aegis_research.models import train_model


def test_ma_sweep_preserves_native_visible_params_and_lineage() -> None:
    close = _close_frame(symbols=["SYN"])
    config = IndicatorConfig(
        specs=[
            IndicatorSpecConfig(
                id="ma",
                params={"window": [2, 3], "wtype": "simple"},
                outputs=["ma"],
                model_features=[
                    IndicatorFeatureConfig(output="ma", transform="distance_to_close"),
                ],
            )
        ]
    )

    result = build_indicator_result(close, config)

    assert "ma" in result.native_objects
    assert result.native_objects["ma"].param_names == ("window", "wtype")
    assert result.native_outputs["ma"]["ma"].columns.names == ["ma_window", "ma_wtype", "symbol"]
    assert result.metadata["specs"][0]["parameter_combinations"] == [
        {"window": 2, "wtype": "simple"},
        {"window": 3, "wtype": "simple"},
    ]
    assert result.frame.columns.names == [
        "feature",
        "indicator",
        "output",
        "transform",
        "params",
        "symbol",
    ]
    assert result.lineage[0]["indicator_id"] == "ma"
    assert result.lineage[0]["transform"] == "distance_to_close"


def test_param_product_records_cartesian_grid_without_run_combs() -> None:
    close = _close_frame(symbols=["SYN"])
    config = IndicatorConfig(
        specs=[
            IndicatorSpecConfig(
                id="ma",
                params={"window": [2, 3], "wtype": ["simple", "wilder"]},
                outputs=["ma"],
                model_features=[IndicatorFeatureConfig(output="ma", transform="distance_to_close")],
                grid="product",
                param_product=True,
            )
        ]
    )

    result = build_indicator_result(close, config)

    assert result.metadata["specs"][0]["grid"] == "product"
    assert result.metadata["specs"][0]["param_product"] is True
    assert len(result.metadata["specs"][0]["parameter_combinations"]) == 4
    assert "run_combs" not in result.metadata["specs"][0]


def test_custom_indicator_factory_definition_matches_builtin_lineage_shape() -> None:
    close = _close_frame(symbols=["AAA", "BBB"])
    config = IndicatorConfig(
        specs=[
            IndicatorSpecConfig(
                id="custom_retvol",
                params={"window": [3]},
                outputs=["retvol"],
                model_features=[IndicatorFeatureConfig(output="retvol")],
            )
        ]
    )

    result = build_indicator_result(close, config)

    symbols = {item["symbol"] for item in result.lineage}

    assert "custom_retvol" in result.native_objects
    assert result.native_outputs["custom_retvol"]["retvol"].columns.names[-1] == "symbol"
    assert symbols == {"AAA", "BBB"}
    assert all(item["indicator_id"] == "custom_retvol" for item in result.lineage)


def test_indicator_stage_fails_fast_for_missing_native_output() -> None:
    close = _close_frame(symbols=["SYN"])
    config = IndicatorConfig(
        specs=[
            IndicatorSpecConfig(
                id="ma",
                params={"window": [2]},
                outputs=["not_ma"],
                model_features=[IndicatorFeatureConfig(output="not_ma")],
            )
        ]
    )

    with pytest.raises(ValueError, match="not_ma"):
        build_indicator_result(close, config)


def test_indicator_stage_rejects_shape_changing_registry_entries(monkeypatch) -> None:
    definition = IndicatorDefinition(
        id="shape_changing_test",
        kind="custom",
        input_names=("close",),
        param_names=("window",),
        output_names=("events",),
        default_outputs=("events",),
        default_model_features=({"output": "events", "transform": "identity"},),
        supported_transforms=("identity",),
        bar_aligned=False,
    )
    monkeypatch.setattr(indicators_module, "get_indicator_definition", lambda _id: definition)
    close = _close_frame(symbols=["SYN"])
    config = IndicatorConfig(
        specs=[
            IndicatorSpecConfig(
                id="shape_changing_test",
                params={"window": [2]},
                outputs=["events"],
                model_features=[IndicatorFeatureConfig(output="events")],
            )
        ]
    )

    with pytest.raises(ValueError, match="bar-aligned"):
        build_indicator_result(close, config)


def test_model_feature_matrix_builds_mapping_and_cleaned_eligible_index() -> None:
    close = _close_frame(symbols=["AAA", "BBB"])
    labels = pd.DataFrame(
        {"AAA": [1, 1, 0, 1, 0, 1, 0, None], "BBB": [1, 0, 1, 0, 1, 0, 1, None]},
        index=close.index,
    )
    config = IndicatorConfig(
        specs=[
            IndicatorSpecConfig(
                id="ma",
                params={"window": [3], "wtype": "simple"},
                outputs=["ma"],
                model_features=[IndicatorFeatureConfig(output="ma", transform="distance_to_close")],
            )
        ]
    )
    indicators = build_indicator_result(close, config)

    matrix = build_model_feature_matrix(indicators, labels, invalid_value_policy="drop_rows")

    assert len(matrix.eligible_index) == 5
    assert matrix.eligible_index[0] == close.index[2]
    assert matrix.eligible_index[-1] == close.index[6]
    assert list(matrix.feature_mapping) == ["ma__ma__distance_to_close__window_3__wtype_simple"]
    assert matrix.feature_mapping["ma__ma__distance_to_close__window_3__wtype_simple"][
        "params"
    ] == {
        "window": 3,
        "wtype": "simple",
    }
    assert matrix.diagnostics["eligible_index"]["count"] == 5
    assert matrix.diagnostics["feature_invalid_row_count"] == 2
    assert matrix.diagnostics["label_invalid_row_count"] == 1
    assert matrix.diagnostics["overlapping_invalid_row_count"] == 0


def test_model_feature_matrix_rejects_label_feature_symbol_mismatch() -> None:
    close = _close_frame(symbols=["AAA"])
    labels = pd.DataFrame({"BBB": [1] * len(close)}, index=close.index)
    indicators = build_indicator_result(close, IndicatorConfig())

    with pytest.raises(ValueError, match="symbol"):
        build_model_feature_matrix(indicators, labels)


def test_model_feature_matrix_records_inf_values_without_silent_replacement() -> None:
    index = pd.date_range("2020-01-01", periods=5, freq="1D", tz="UTC", name="Open time")
    close = pd.DataFrame({"SYN": [0.0, 1.0, 2.0, 3.0, 4.0]}, index=index)
    labels = pd.DataFrame({"SYN": [1, 1, 1, 1, 1]}, index=index)
    config = IndicatorConfig(
        specs=[
            IndicatorSpecConfig(
                id="returns",
                params={"window": [1]},
                outputs=["returns"],
                model_features=[IndicatorFeatureConfig(output="returns")],
            )
        ]
    )
    indicators = build_indicator_result(close, config)

    matrix = build_model_feature_matrix(indicators, labels, invalid_value_policy="drop_rows")

    assert matrix.diagnostics["total_inf_count"] == 1
    assert len(matrix.eligible_index) == 3
    assert matrix.frame.isin([float("inf"), float("-inf")]).sum().sum() == 0


def test_model_feature_matrix_raise_policy_rejects_invalid_rows() -> None:
    close = _close_frame(symbols=["SYN"])
    labels = pd.DataFrame({"SYN": [1] * len(close)}, index=close.index)
    config = IndicatorConfig(
        specs=[
            IndicatorSpecConfig(
                id="ma",
                params={"window": [3], "wtype": "simple"},
                outputs=["ma"],
                model_features=[IndicatorFeatureConfig(output="ma", transform="distance_to_close")],
            )
        ]
    )
    indicators = build_indicator_result(close, config)

    with pytest.raises(ValueError, match="Invalid feature or label values"):
        build_model_feature_matrix(indicators, labels, invalid_value_policy="raise")


def test_training_boundary_rejects_colliding_feature_names() -> None:
    index = pd.date_range("2020-01-01", periods=8, freq="1D", tz="UTC", name="Open time")
    indicators = pd.DataFrame(
        [[0.1, 0.2]] * len(index),
        index=index,
        columns=pd.MultiIndex.from_tuples(
            [
                ("same_feature", "first", "out", "identity", "{}", "SYN"),
                ("same_feature", "second", "out", "identity", "{}", "SYN"),
            ],
            names=["feature", "indicator", "output", "transform", "params", "symbol"],
        ),
    )
    labels = pd.DataFrame({"SYN": [0, 1, 0, 1, 0, 1, 0, 1]}, index=index)

    with pytest.raises(ValueError, match="collide"):
        train_model(indicators, labels, ModelConfig(min_train_samples=1))


def _close_frame(symbols: list[str]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=8, freq="1D", tz="UTC", name="Open time")
    data = {
        symbol: [float(offset + index_value + 1) for index_value in range(len(index))]
        for offset, symbol in enumerate(symbols)
    }
    return pd.DataFrame(data, index=index)
