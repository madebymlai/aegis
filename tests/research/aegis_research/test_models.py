from __future__ import annotations

import pandas as pd
import pytest

from research.aegis_research.config import ModelConfig
from research.aegis_research.models import (
    TargetModelCompatibilityError,
    assert_target_model_compatible,
    target_model_compatibility,
    train_model,
)
from research.aegis_research.splits import ValidationSplit


def test_continuous_target_fails_before_sklearn() -> None:
    diagnostics = target_model_compatibility(
        _labels([0.1, 0.2, 0.3]),
        ModelConfig(min_train_samples=1),
        _target_schema("continuous"),
        phase="pre_split",
    )

    with pytest.raises(TargetModelCompatibilityError, match="binary classification"):
        assert_target_model_compatible(diagnostics)


def test_binary_target_with_one_class_in_train_split_fails() -> None:
    index = pd.RangeIndex(4)
    diagnostics = target_model_compatibility(
        _labels([1, 1, 0, 0], index=index),
        ModelConfig(min_train_samples=1),
        _target_schema("binary_classification"),
        [ValidationSplit(label="holdout", train_index=index[:2], test_index=index[2:])],
        phase="post_split",
    )

    with pytest.raises(TargetModelCompatibilityError, match="both classes"):
        assert_target_model_compatible(diagnostics)
    assert diagnostics["splits"][0]["train_class_counts"] == {"1": 2}


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
        ModelConfig(min_train_samples=2),
        _target_schema("binary_classification"),
        [ValidationSplit(label="holdout", train_index=index, test_index=index[2:])],
        phase="post_split",
    )

    assert_target_model_compatible(diagnostics)
    model = train_model(indicators, labels, ModelConfig(min_train_samples=2))

    assert model is not None


def _labels(values, *, index=None) -> pd.DataFrame:
    return pd.DataFrame({"SYN": values}, index=index)


def _target_schema(target_kind: str) -> dict[str, object]:
    return {
        "target_kind": target_kind,
        "target_role": "supervised_target",
        "split_safety": {
            "purging_required": True,
            "purging_applied": False,
            "leakage_risk": "fixed_unpurged",
        },
    }
