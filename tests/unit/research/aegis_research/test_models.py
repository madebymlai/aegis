from __future__ import annotations

import pandas as pd
import pytest

from research.aegis_research.config import TrainModelConfig
from research.aegis_research.model_contracts import ModelPredictionResult
from research.aegis_research.models import (
    TargetModelCompatibilityError,
    _positive_probability_series,
    assert_target_model_compatible,
    target_model_compatibility,
    train_model,
)
from research.aegis_research.splits import ValidationSplit
from tests.support.research.aegis_research.model_plugin_fixtures import (
    make_model_registry,
    model_config_dict,
)


def test_continuous_target_fails_before_sklearn() -> None:
    diagnostics = target_model_compatibility(
        _labels([0.1, 0.2, 0.3]),
        _model_config(),
        _target_schema("continuous"),
        phase="pre_split",
        model_registry=make_model_registry(),
    )

    with pytest.raises(TargetModelCompatibilityError, match="binary classification"):
        assert_target_model_compatible(diagnostics)


def test_binary_target_with_one_class_in_train_split_fails() -> None:
    index = pd.RangeIndex(4)
    diagnostics = target_model_compatibility(
        _labels([1, 1, 0, 0], index=index),
        _model_config(),
        _target_schema("binary_classification"),
        [ValidationSplit(label="split_0", train_index=index[:2], test_index=index[2:])],
        phase="post_split",
        model_registry=make_model_registry(),
    )

    with pytest.raises(TargetModelCompatibilityError, match="both classes"):
        assert_target_model_compatible(diagnostics)
    assert diagnostics["splits"][0]["train_class_counts"] == {"int:1": 2}


def test_regime_target_fails_even_when_values_are_binary() -> None:
    diagnostics = target_model_compatibility(
        _labels([0, 1, 0, 1]),
        _model_config(),
        _target_schema("binary_classification", target_role="regime"),
        phase="pre_split",
        model_registry=make_model_registry(),
    )

    with pytest.raises(TargetModelCompatibilityError, match="supervised_target"):
        assert_target_model_compatible(diagnostics)


def test_pre_split_lookahead_target_does_not_require_purging_proof_yet() -> None:
    diagnostics = target_model_compatibility(
        _labels([0, 1, 0, 1]),
        _model_config(),
        _target_schema(
            "binary_classification",
            split_safety={"purging_required": True, "purging_applied": False},
        ),
        phase="pre_split",
        model_registry=make_model_registry(),
    )

    assert_target_model_compatible(diagnostics)


def test_post_split_unpurged_lookahead_target_requires_purging_proof() -> None:
    index = pd.RangeIndex(4)
    diagnostics = target_model_compatibility(
        _labels([0, 1, 0, 1], index=index),
        _model_config(),
        _target_schema(
            "binary_classification",
            split_safety={"purging_required": True, "purging_applied": False},
        ),
        [ValidationSplit(label="unpurged", train_index=index[:2], test_index=index[2:])],
        phase="post_split",
        model_registry=make_model_registry(),
    )

    with pytest.raises(TargetModelCompatibilityError, match="purged split evidence"):
        assert_target_model_compatible(diagnostics)


def test_post_split_purged_lookahead_target_uses_split_proof() -> None:
    index = pd.RangeIndex(4)
    diagnostics = target_model_compatibility(
        _labels([0, 1, 0, 1], index=index),
        _model_config(),
        _target_schema(
            "binary_classification",
            split_safety={"purging_required": True, "purging_applied": False},
        ),
        [ValidationSplit(label="purged", train_index=index[:2], test_index=index[2:])],
        phase="post_split",
        split_metadata={"purging_applied": True, "leakage_invariant": {"passed": True}},
        model_registry=make_model_registry(),
    )

    assert_target_model_compatible(diagnostics)
    assert diagnostics["split_safety"]["purging_applied"] is True


def test_valid_binary_target_reaches_training() -> None:
    index = pd.RangeIndex(4)
    indicators = pd.DataFrame(
        [[0.0], [1.0], [2.0], [3.0]],
        index=index,
        columns=pd.MultiIndex.from_tuples(
            [("returns", "returns", "returns", "identity", "{}", "SYN")],
            names=["feature", "indicator", "output", "transform", "params", "symbol"],
        ),
    )
    labels = _labels([0, 1, 0, 1], index=index)
    diagnostics = target_model_compatibility(
        labels,
        _model_config(min_train_samples=2),
        _target_schema("binary_classification"),
        [ValidationSplit(label="split_0", train_index=index, test_index=index[2:])],
        phase="post_split",
        model_registry=make_model_registry(),
    )

    assert_target_model_compatible(diagnostics)
    model = train_model(
        indicators,
        labels,
        _model_config(min_train_samples=2),
        model_registry=make_model_registry(),
        target_schema=_target_schema("binary_classification"),
        split_label="split_0",
    )

    assert model is not None
    assert "params" not in model.metadata["config"]
    assert set(model.metadata["diagnostics"]) == {"dataset"}


def test_probability_series_must_name_positive_class_output() -> None:
    index = pd.MultiIndex.from_product(
        [pd.RangeIndex(2), ["SYN"]], names=[None, "symbol"]
    )
    result = ModelPredictionResult(
        probabilities=pd.Series([0.8, 0.7], index=index, name="class_0_probability"),
        observed_classes=(0, 1),
        class_probability_columns={0: "class_0_probability", 1: "class_1_probability"},
    )

    with pytest.raises(ValueError, match="positive class"):
        _positive_probability_series(result, _target_schema("binary_classification"))


def _labels(values, *, index=None) -> pd.DataFrame:
    return pd.DataFrame({"SYN": values}, index=index)


def _model_config(min_train_samples: int = 1) -> TrainModelConfig:
    raw = model_config_dict(min_train_samples=min_train_samples)
    return TrainModelConfig(
        source="plugin",
        id=raw["plugin_id"],
        min_train_samples=raw["min_train_samples"],
        params=raw["params"],
    )


def _target_schema(
    target_kind: str,
    *,
    target_role: str = "supervised_target",
    split_safety: dict[str, object] | None = None,
) -> dict[str, object]:
    schema: dict[str, object] = {
        "target_kind": target_kind,
        "target_role": target_role,
    }
    if target_kind == "binary_classification":
        schema["classes"] = [
            {"label": 0, "role": "negative", "canonical": "int:0"},
            {"label": 1, "role": "positive", "canonical": "int:1"},
        ]
        schema["positive_class"] = 1
    if split_safety is not None:
        schema["split_safety"] = split_safety
    return schema
