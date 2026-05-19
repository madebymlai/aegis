from __future__ import annotations

import pandas as pd
import pytest

from research.aegis_research.data import (
    close_from_ohlcv,
    feature_from_ohlcv,
    high_from_ohlcv,
    load_market_data,
    low_from_ohlcv,
)
from research.aegis_research.indicators import build_model_feature_matrix
from research.aegis_research.labels import LabelConfig, build_label_result
from research.aegis_research.models import target_model_compatibility
from research.aegis_research.splits import build_validation_splits_result
from research.aegis_research.validation import (
    _aggregate_metrics,
    _decision_grade,
    evaluate_validation_splits,
)
from tests.support.research.aegis_research.experiment_config_fixtures import (
    SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG,
    load_train_fixture_config,
)
from tests.support.research.aegis_research.model_plugin_fixtures import make_model_registry
from tests.support.research.aegis_research.indicator_result_fixtures import native_indicator_result


def test_validation_result_exposes_complete_split_child_shape() -> None:
    result = _evaluate(SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG)

    assert len(result.split_results) == 5
    assert len(result.split_metric_evidence) == 10
    assert result.validation_metadata["n_splits"] == 5
    assert result.validation_metadata["decision_grade"] is True
    assert result.validation_metadata["split_metadata"]["purging_applied"] is True
    assert result.validation_metadata["portfolio_execution_timing_checked"] is True
    assert result.validation_metadata["signal_policy"]["name"] == "long_only_hysteresis"
    assert result.validation_metadata["portfolio_metric_assumptions"]["scope"] == (
        "shared_cash_group"
    )
    assert result.validation_metadata["portfolio_metric_assumptions"]["benchmark_status"] == "none"
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
        assert split.test_metrics["metric_scope"] == "shared_cash_group"
        assert split.test_metrics["metric_assumptions"]["freq"] == "1D"
        assert split.test_metrics["metric_assumptions"]["benchmark_status"] == "none"
        assert split.test_metrics["metric_evidence"]["sharpe_ratio"]["availability"] in {
            "available",
            "unavailable_metric",
        }
    assert result.test_metrics["metric_scope"] == "shared_cash_group"
    assert result.test_metrics["metric_assumptions"]["year_freq"] == "252D"
    test_evidence = [row for row in result.split_metric_evidence if row["set"] == "test"]
    assert test_evidence[0]["metric_evidence"]["sharpe_ratio"]["source"]["identity"] == (
        "sharpe_ratio"
    )
    assert "metric_evidence" not in result.split_metrics.columns


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


def test_aggregate_metrics_rejects_mixed_metric_assumptions() -> None:
    metrics = _metrics_frame(
        [
            {"scope": "shared_cash_group", "year_freq": "252D"},
            {"scope": "shared_cash_group", "year_freq": "365D"},
        ]
    )

    with pytest.raises(ValueError, match="metric_assumptions"):
        _aggregate_metrics(metrics)


def test_aggregate_metrics_rejects_mixed_metric_scope() -> None:
    metrics = _metrics_frame(
        [
            {"scope": "shared_cash_group", "year_freq": "252D"},
            {"scope": "other", "year_freq": "252D"},
        ]
    )
    metrics.loc["split_1", "metric_scope"] = "other"

    with pytest.raises(ValueError, match="metric_scope"):
        _aggregate_metrics(metrics)


def test_aggregate_metrics_requires_metric_metadata_for_every_row() -> None:
    metrics = _metrics_frame(
        [
            {"scope": "shared_cash_group", "year_freq": "252D"},
            None,
        ]
    )

    with pytest.raises(ValueError, match="metric_assumptions"):
        _aggregate_metrics(metrics)


def test_validation_requires_open_prices_for_default_next_open() -> None:
    with pytest.raises(ValueError, match="open prices"):
        _evaluate(
            SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG,
            pass_open_prices=False,
        )


def _evaluate(config_path: str, *, pass_open_prices: bool = True):
    registry = make_model_registry()
    resolved = load_train_fixture_config(config_path, model_registry=registry)
    config = resolved.config
    data = load_market_data(config.data)
    close = close_from_ohlcv(data)
    open_prices = feature_from_ohlcv(data, "Open") if pass_open_prices else None
    high = high_from_ohlcv(data)
    low = low_from_ohlcv(data)
    indicator_result = native_indicator_result(close)
    label_result = build_label_result(close, LabelConfig(), high=high, low=low)
    labels = label_result.labels
    model_features = build_model_feature_matrix(
        indicator_result,
        labels,
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


def _metrics_frame(metric_assumptions: list[dict[str, object] | None]):
    return pd.DataFrame(
        {
            "total_return_pct": [1.0, 2.0],
            "sharpe_ratio": [1.0, 2.0],
            "max_drawdown_pct": [1.0, 2.0],
            "total_trades": [1, 2],
            "win_rate_pct": [50.0, 60.0],
            "total_fees_paid": [0.0, 0.0],
            "metric_scope": ["shared_cash_group", "shared_cash_group"],
            "metric_assumptions": metric_assumptions,
        },
        index=["split_0", "split_1"],
    )
