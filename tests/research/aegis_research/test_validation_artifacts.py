from __future__ import annotations

from research.aegis_research.config import load_experiment_config
from research.aegis_research.data import (
    close_from_ohlcv,
    high_from_ohlcv,
    load_market_data,
    low_from_ohlcv,
)
from research.aegis_research.indicators import build_indicator_result, build_model_feature_matrix
from research.aegis_research.labels import build_labels
from research.aegis_research.splits import build_validation_splits
from research.aegis_research.validation import evaluate_validation_splits


def test_validation_result_exposes_complete_split_child_shape() -> None:
    result = _evaluate("research/configs/experiments/synthetic_walkforward_baseline.yaml")

    assert len(result.split_results) == 5
    assert result.validation_metadata["n_splits"] == 5
    for split in result.split_results:
        assert split.model is not None
        assert list(split.train_probabilities.columns) == ["SYN"]
        assert list(split.test_probabilities.columns) == ["SYN"]
        assert all(str(dtype) == "bool" for dtype in split.train_entries.dtypes)
        assert all(str(dtype) == "bool" for dtype in split.test_entries.dtypes)
        assert split.train_portfolio is not None
        assert split.test_portfolio is not None
        assert split.train_metrics
        assert split.test_metrics
        assert split.metadata["label"] == split.label
        assert split.metadata["sets"]["train"]["rows"] > 0
        assert split.metadata["sets"]["test"]["rows"] > 0


def test_holdout_uses_same_one_split_result_shape() -> None:
    result = _evaluate("research/configs/experiments/synthetic_ml_baseline.yaml")

    assert len(result.split_results) == 1
    split = result.split_results[0]
    assert split.label == "holdout"
    assert split.train_portfolio is not None
    assert split.test_portfolio is not None
    assert result.validation_metadata["kind"] == "holdout"
    assert result.validation_metadata["n_splits"] == 1


def _evaluate(config_path: str):
    resolved = load_experiment_config(config_path)
    config = resolved.config
    data = load_market_data(config.data)
    close = close_from_ohlcv(data)
    high = high_from_ohlcv(data)
    low = low_from_ohlcv(data)
    indicator_result = build_indicator_result(close, config.indicators)
    labels = build_labels(close, config.labels, high=high, low=low)
    model_features = build_model_feature_matrix(
        indicator_result,
        labels,
        invalid_value_policy=config.indicators.invalid_value_policy,
    )
    splits = build_validation_splits(
        model_features.eligible_index,
        config.split,
    )
    return evaluate_validation_splits(close, model_features.frame, labels, splits, config)
