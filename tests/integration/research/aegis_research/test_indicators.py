from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.component_registry.contracts import ComponentRegistryError
from research.aegis_research.config import RunIndicatorSourceConfig, TrainModelConfig
from research.aegis_research.indicators import (
    build_component_indicator_result,
    build_model_feature_matrix,
)
from research.aegis_research.market_data.contracts import MarketDataBundle
from research.aegis_research.models import train_model
from tests.support.research.aegis_research.indicator_result_fixtures import (
    ma_indicator_result,
    returns_indicator_result,
)
from tests.support.research.aegis_research.model_plugin_fixtures import (
    make_model_registry,
    model_config_dict,
)


def test_component_indicator_preserves_vbt_param_lineage(tmp_path: Path) -> None:
    close = _close_frame(symbols=["SYN"])

    result = _component_result(
        tmp_path,
        close,
        _indicator_manifest("demo.ma", param_names=["window", "wtype"]),
        "from vectorbtpro import vbt\n"
        "def run(data):\n"
        "    ma = vbt.MA.run(data.feature('Close'), window=[2, 3], wtype='simple', "
        "hide_params=None, hide_default=False)\n"
        "    return ma.ma\n",
    )

    assert result.native_outputs["demo.ma"]["ma"].columns.names == [
        "ma_window",
        "ma_wtype",
        "symbol",
    ]
    assert result.metadata["components"][0]["params"] == [
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
    assert result.lineage[0]["indicator_id"] == "demo.ma"
    assert result.lineage[0]["transform"] == "distance_to_close"
    assert result.lineage[0]["params"] == {"window": 2, "wtype": "simple"}


def test_component_indicator_records_cartesian_vbt_grid(tmp_path: Path) -> None:
    close = _close_frame(symbols=["SYN"])

    result = _component_result(
        tmp_path,
        close,
        _indicator_manifest("demo.ma", param_names=["window", "wtype"]),
        "from vectorbtpro import vbt\n"
        "def run(data):\n"
        "    ma = vbt.MA.run(data.feature('Close'), window=[2, 3], wtype=['simple', 'wilder'], "
        "param_product=True, hide_params=None, hide_default=False)\n"
        "    return ma.ma\n",
    )

    assert len(result.metadata["components"][0]["params"]) == 4
    assert {tuple(sorted(item["params"].items())) for item in result.lineage} == {
        (("window", 2), ("wtype", "simple")),
        (("window", 2), ("wtype", "wilder")),
        (("window", 3), ("wtype", "simple")),
        (("window", 3), ("wtype", "wilder")),
    }


def test_custom_indicator_factory_component_matches_builtin_lineage_shape(tmp_path: Path) -> None:
    close = _close_frame(symbols=["AAA", "BBB"])

    result = _component_result(
        tmp_path,
        close,
        _indicator_manifest(
            "demo.retvol",
            param_names=["window"],
            output_name="retvol",
            transforms=["identity"],
        ),
        "from vectorbtpro import vbt\n"
        "def _retvol_apply(close, window):\n"
        "    return close.pct_change().rolling(window).std()\n"
        "RETVOL = vbt.IF(input_names=['close'], param_names=['window'], "
        "output_names=['retvol']).with_apply_func(_retvol_apply, keep_pd=True)\n"
        "def run(data):\n"
        "    return RETVOL.run(data.feature('Close'), window=[3], hide_params=None, hide_default=False).retvol\n",
    )

    symbols = {item["symbol"] for item in result.lineage}

    assert result.native_outputs["demo.retvol"]["retvol"].columns.names[-1] == "symbol"
    assert symbols == {"AAA", "BBB"}
    assert all(item["indicator_id"] == "demo.retvol" for item in result.lineage)


def test_component_indicator_reads_declared_bundle_features(tmp_path: Path) -> None:
    close = _close_frame(symbols=["SYN"])
    high = close + 2.0

    result = _component_result(
        tmp_path,
        close,
        _indicator_manifest(
            "demo.high_gap",
            input_names=["High", "Close"],
            output_name="high_gap",
            transforms=["identity"],
        ),
        "def run(data):\n"
        "    return data.feature('High') - data.feature('Close')\n",
        high=high,
    )

    assert result.frame.iloc[-1, 0] == 2.0
    assert result.lineage[0]["output"] == "high_gap"


def test_component_indicator_rejects_default_model_feature_for_unknown_output(tmp_path: Path) -> None:
    close = _close_frame(symbols=["SYN"])
    manifest = _indicator_manifest("demo.bad", model_output="not_ma")

    with pytest.raises(ComponentRegistryError, match="default_model_features"):
        _component_result(
            tmp_path,
            close,
            manifest,
            "def run(data):\n"
            "    return data.feature('Close').rolling(2).mean()\n",
        )


def test_component_indicator_rejects_shape_changing_outputs(tmp_path: Path) -> None:
    close = _close_frame(symbols=["SYN"])

    with pytest.raises(ValueError, match="bar-aligned"):
        _component_result(
            tmp_path,
            close,
            _indicator_manifest("demo.bad"),
            "def run(data):\n"
            "    return data.feature('Close').iloc[1:]\n",
        )


def test_model_feature_matrix_builds_mapping_and_cleaned_eligible_index() -> None:
    close = _close_frame(symbols=["AAA", "BBB"])
    labels = pd.DataFrame(
        {"AAA": [1, 1, 0, 1, 0, 1, 0, None], "BBB": [1, 0, 1, 0, 1, 0, 1, None]},
        index=close.index,
    )
    indicators = ma_indicator_result(close, windows=[3])

    matrix = build_model_feature_matrix(indicators, labels, invalid_value_policy="drop_rows")

    assert len(matrix.eligible_index) == 5
    assert matrix.eligible_index[0] == close.index[2]
    assert matrix.eligible_index[-1] == close.index[6]
    assert list(matrix.feature_mapping) == ["ma__ma__distance_to_close__window_3__wtype_simple"]
    assert matrix.feature_mapping["ma__ma__distance_to_close__window_3__wtype_simple"]["params"] == {
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
    indicators = returns_indicator_result(close)

    with pytest.raises(ValueError, match="symbol"):
        build_model_feature_matrix(indicators, labels)


def test_model_feature_matrix_records_inf_values_without_silent_replacement() -> None:
    index = pd.date_range("2020-01-01", periods=5, freq="1D", tz="UTC", name="Open time")
    close = pd.DataFrame({"SYN": [0.0, 1.0, 2.0, 3.0, 4.0]}, index=index)
    labels = pd.DataFrame({"SYN": [1, 1, 1, 1, 1]}, index=index)
    indicators = returns_indicator_result(close)

    matrix = build_model_feature_matrix(indicators, labels, invalid_value_policy="drop_rows")

    assert matrix.diagnostics["total_inf_count"] == 1
    assert len(matrix.eligible_index) == 3
    assert matrix.frame.isin([float("inf"), float("-inf")]).sum().sum() == 0


def test_model_feature_matrix_raise_policy_rejects_invalid_rows() -> None:
    close = _close_frame(symbols=["SYN"])
    labels = pd.DataFrame({"SYN": [1] * len(close)}, index=close.index)
    indicators = ma_indicator_result(close, windows=[3])

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
        train_model(
            indicators,
            labels,
            _train_model_config(min_train_samples=1),
            model_registry=make_model_registry(),
            target_schema={
                "target_kind": "binary_classification",
                "target_role": "supervised_target",
                "classes": [
                    {"label": 0, "role": "negative", "canonical": "int:0"},
                    {"label": 1, "role": "positive", "canonical": "int:1"},
                ],
                "positive_class": 1,
            },
            split_label="split_0",
        )


def _component_result(
    tmp_path: Path,
    close: pd.DataFrame,
    manifest: dict[str, object],
    source: str,
    *,
    high: pd.DataFrame | None = None,
):
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "indicator.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        f"{source}"
    )
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    features = {"Close": close}
    if high is not None:
        features["High"] = high
    return build_component_indicator_result(
        MarketDataBundle(features=features, loaded_features=tuple(features)),
        [RunIndicatorSourceConfig(source="component", ids=[str(manifest["id"])])],
        component_registry=registry,
    )


def _train_model_config(min_train_samples: int) -> TrainModelConfig:
    raw = model_config_dict(min_train_samples=min_train_samples)
    return TrainModelConfig(
        source="plugin",
        id=raw["plugin_id"],
        min_train_samples=raw["min_train_samples"],
        params=raw["params"],
    )


def _indicator_manifest(
    component_id: str,
    *,
    input_names: list[str] | None = None,
    param_names: list[str] | None = None,
    output_name: str = "ma",
    model_output: str | None = None,
    transforms: list[str] | None = None,
) -> dict[str, object]:
    transform = (transforms or ["identity", "distance_to_close"])[-1]
    return {
        "family": "indicators",
        "id": component_id,
        "version": "1.0.0",
        "input_names": input_names or ["Close"],
        "param_names": param_names or [],
        "output_names": [output_name],
        "default_outputs": [output_name],
        "default_model_features": [
            {"output": model_output or output_name, "transform": transform}
        ],
        "supported_transforms": transforms or ["identity", "distance_to_close"],
    }


def _close_frame(symbols: list[str]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=8, freq="1D", tz="UTC", name="Open time")
    data = {
        symbol: [float(offset + index_value + 1) for index_value in range(len(index))]
        for offset, symbol in enumerate(symbols)
    }
    return pd.DataFrame(data, index=index)
