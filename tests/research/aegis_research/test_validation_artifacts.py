from __future__ import annotations

import pytest

from research.aegis_research.config import load_experiment_config
from research.aegis_research.data import (
    close_from_ohlcv,
    feature_from_ohlcv,
    high_from_ohlcv,
    load_market_data,
    low_from_ohlcv,
)
from research.aegis_research.indicators import build_indicator_result, build_model_feature_matrix
from research.aegis_research.labels import build_label_result
from research.aegis_research.models import target_model_compatibility
from research.aegis_research.splits import build_validation_splits_result
from research.aegis_research.validation import _decision_grade, evaluate_validation_splits
from tests.research.aegis_research.model_plugin_fixtures import make_model_registry


def test_validation_result_exposes_complete_split_child_shape() -> None:
    result = _evaluate("research/configs/experiments/synthetic_purged_fixlb_baseline.yaml")

    assert len(result.split_results) == 5
    assert result.validation_metadata["n_splits"] == 5
    assert result.validation_metadata["decision_grade"] is True
    assert result.validation_metadata["split_metadata"]["purging_applied"] is True
    assert result.validation_metadata["portfolio_execution_timing_checked"] is True
    assert result.validation_metadata["signal_policy"]["name"] == "long_only_hysteresis"
    assert result.signal_diagnostics["splits"]
    assert result.portfolio_diagnostics["splits"]
    for split in result.split_results:
        assert split.model is not None
        assert list(split.train_probabilities.columns) == ["SYN"]
        assert list(split.test_probabilities.columns) == ["SYN"]
        assert all(str(dtype) == "bool" for dtype in split.train_entries.dtypes)
        assert all(str(dtype) == "bool" for dtype in split.test_entries.dtypes)
        assert split.train_portfolio is not None
        assert split.test_portfolio is not None
        assert split.train_signal_diagnostics["set_name"] == "train"
        assert split.test_signal_diagnostics["set_name"] == "test"
        assert split.train_signal_diagnostics["probability"]["source_output_name"] == (
            "positive_class_probability"
        )
        assert split.train_portfolio_diagnostics["execution"]["timing"] == "next_open"
        assert "order_count" in split.test_portfolio_diagnostics["records"]
        assert split.train_metrics
        assert split.test_metrics
        assert split.metadata["label"] == split.label
        assert split.metadata["signals"]["train"]["split_id"] == split.label
        assert split.metadata["portfolios"]["test"]["execution"]["timing"] == "next_open"
        assert split.metadata["sets"]["train"]["rows"] > 0
        assert split.metadata["sets"]["test"]["rows"] > 0


def test_decision_grade_requires_split_purging_proof() -> None:
    target_schema = {"split_safety": {"purging_required": True, "purging_applied": False}}

    assert _decision_grade(None, split_metadata=None, compatibility=None) is False
    assert _decision_grade(target_schema, split_metadata=None, compatibility=None) is False
    assert (
        _decision_grade(
            target_schema,
            split_metadata={"purging_applied": True, "leakage_invariant": {"passed": True}},
            compatibility={"compatible": True},
        )
        is True
    )


def test_validation_requires_open_prices_for_default_next_open() -> None:
    with pytest.raises(ValueError, match="open prices"):
        _evaluate(
            "research/configs/experiments/synthetic_purged_fixlb_baseline.yaml",
            pass_open_prices=False,
        )


def _evaluate(config_path: str, *, pass_open_prices: bool = True):
    registry = make_model_registry()
    resolved = load_experiment_config(config_path, model_registry=registry)
    config = resolved.config
    data = load_market_data(config.data)
    close = close_from_ohlcv(data)
    open_prices = feature_from_ohlcv(data, "Open") if pass_open_prices else None
    high = high_from_ohlcv(data)
    low = low_from_ohlcv(data)
    indicator_result = build_indicator_result(close, config.indicators)
    label_result = build_label_result(close, config.labels, high=high, low=low)
    labels = label_result.labels
    model_features = build_model_feature_matrix(
        indicator_result,
        labels,
        invalid_value_policy=config.indicators.invalid_value_policy,
    )
    splits_result = build_validation_splits_result(
        model_features.eligible_index,
        config.split,
        target_metadata={"split_safety": label_result.split_safety},
        evaluation_evidence=label_result.evaluation_evidence,
    )
    compatibility = target_model_compatibility(
        labels,
        config.model,
        label_result.target_schema,
        splits_result.splits,
        phase="post_split",
        split_metadata=splits_result.metadata,
        model_registry=registry,
    )
    return evaluate_validation_splits(
        close,
        model_features.frame,
        labels,
        splits_result.splits,
        config,
        open_prices=open_prices,
        target_schema=label_result.target_schema,
        split_metadata=splits_result.metadata,
        compatibility=compatibility,
        model_registry=registry,
    )
