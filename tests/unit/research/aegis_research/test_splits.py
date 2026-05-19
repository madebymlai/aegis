import pandas as pd
import pytest

from research.aegis_research.config import SplitConfig
from research.aegis_research.labels import (
    LabelConfig,
    LabelEvaluationEvidence,
    LabelGeneratorConfig,
    LabelTargetConfig,
    LabelTargetTransformConfig,
    build_label_result,
)
from research.aegis_research.splits import (
    ValidationSplit,
    _assert_no_interval_leakage,
    _row_level_prediction_evaluation_times,
    build_validation_splits_result,
)


def test_purged_kfold_builds_membership_evidence_from_fixlb_eval_times() -> None:
    index = pd.date_range("2024-01-01", periods=18, freq="D")
    close = pd.DataFrame({"SYN": range(1, 19)}, index=index, dtype=float)
    label_result = build_label_result(
        close,
        _fixlb_config(n=2),
    )
    eligible_index = label_result.labels.dropna().index

    result = build_validation_splits_result(
        eligible_index,
        SplitConfig(
            kind="purged_kfold",
            n_folds=4,
            n_test_folds=1,
            purge_td="0D",
            embargo_td="0D",
        ),
        target_metadata={"split_safety": label_result.split_safety},
        evaluation_evidence=label_result.evaluation_evidence,
    )

    assert result.metadata["kind"] == "purged_kfold"
    assert result.metadata["purging_applied"] is True
    assert result.metadata["leakage_invariant"]["passed"] is True
    assert result.metadata["n_splits"] == 4
    assert result.metadata["resource_estimate"]["split_count"] == 4
    assert result.metadata["time_validation"]["pred_times_explicit"] is True
    assert len(result.metadata["sample_intervals"]) == len(eligible_index)
    assert result.metadata["sample_intervals"][0]["timestamp"] == eligible_index[0].isoformat()
    assert result.metadata["sample_intervals"][0]["prediction_time"] == eligible_index[0].isoformat()
    assert result.metadata["sample_intervals"][0]["evaluation_time"] == eligible_index[2].isoformat()
    assert "membership" in result.metadata["splits"][0]["train"]
    assert "membership" in result.metadata["splits"][0]["test"]
    assert all(split.train_index.intersection(split.test_index).empty for split in result.splits)


def test_purged_kfold_requires_datetime_prediction_times() -> None:
    close = pd.DataFrame({"SYN": range(1, 10)}, dtype=float)
    label_result = build_label_result(close, _fixlb_config(n=2))
    eligible_index = label_result.labels.dropna().index

    with pytest.raises(TypeError, match="datetime-like"):
        build_validation_splits_result(
            eligible_index,
            SplitConfig(kind="purged_kfold"),
            evaluation_evidence=label_result.evaluation_evidence,
        )


def test_purged_kfold_fails_when_eval_time_is_missing_for_selected_row() -> None:
    index = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.DataFrame({"SYN": range(1, 11)}, index=index, dtype=float)
    label_result = build_label_result(close, _fixlb_config(n=2))
    eligible_index = label_result.labels.dropna().index
    evidence = label_result.evaluation_evidence
    evidence.evaluation_times.loc[eligible_index[0], "SYN"] = pd.NaT

    with pytest.raises(ValueError, match="evaluation time"):
        build_validation_splits_result(
            eligible_index,
            SplitConfig(kind="purged_kfold"),
            evaluation_evidence=evidence,
        )


def test_purged_kfold_requires_evaluation_evidence() -> None:
    index = pd.date_range("2024-01-01", periods=10, freq="D")

    with pytest.raises(ValueError, match="label evaluation evidence"):
        build_validation_splits_result(index, SplitConfig(kind="purged_kfold"))


def test_purged_kfold_rejects_variable_unknown_label_evidence() -> None:
    index = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.DataFrame({"SYN": [1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0, 4.0, 3.0, 2.0]}, index=index)
    label_result = build_label_result(
        close,
        _pivot_config(),
        high=close * 1.01,
        low=close * 0.99,
    )
    eligible_index = label_result.labels.dropna().index

    with pytest.raises(ValueError, match="evaluation time"):
        build_validation_splits_result(
            eligible_index,
            SplitConfig(kind="purged_kfold"),
            evaluation_evidence=label_result.evaluation_evidence,
        )


def test_purged_kfold_resource_guard_runs_before_validation_work() -> None:
    index = pd.date_range("2024-01-01", periods=18, freq="D")
    close = pd.DataFrame({"SYN": range(1, 19)}, index=index, dtype=float)
    label_result = build_label_result(close, _fixlb_config(n=2))
    eligible_index = label_result.labels.dropna().index

    with pytest.raises(ValueError, match="estimated output cells"):
        build_validation_splits_result(
            eligible_index,
            SplitConfig(kind="purged_kfold", n_folds=4, max_estimated_output_cells=1),
            evaluation_evidence=label_result.evaluation_evidence,
        )


def test_pairwise_leakage_invariant_rejects_overlapping_intervals() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="D")
    split = ValidationSplit(label="bad", train_index=index[[0]], test_index=index[[1]])
    pred_times = pd.Series(index, index=index)
    eval_times = pd.Series(index + pd.Timedelta(days=3), index=index)

    with pytest.raises(ValueError, match="overlaps"):
        _assert_no_interval_leakage(
            [split],
            pred_times,
            eval_times,
            purge_td=pd.Timedelta(0),
            embargo_td=pd.Timedelta(0),
        )


def test_pairwise_leakage_invariant_applies_nonzero_purge_and_embargo() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="D")
    pred_times = pd.Series(index, index=index)
    eval_times = pd.Series(index, index=index)

    with pytest.raises(ValueError, match="overlaps"):
        _assert_no_interval_leakage(
            [ValidationSplit(label="purge", train_index=index[[0]], test_index=index[[1]])],
            pred_times,
            eval_times,
            purge_td=pd.Timedelta(days=1),
            embargo_td=pd.Timedelta(0),
        )

    with pytest.raises(ValueError, match="overlaps"):
        _assert_no_interval_leakage(
            [ValidationSplit(label="embargo", train_index=index[[2]], test_index=index[[1]])],
            pred_times,
            eval_times,
            purge_td=pd.Timedelta(0),
            embargo_td=pd.Timedelta(days=1),
        )

    result = _assert_no_interval_leakage(
        [ValidationSplit(label="safe", train_index=index[[3]], test_index=index[[1]])],
        pred_times,
        eval_times,
        purge_td=pd.Timedelta(days=1),
        embargo_td=pd.Timedelta(days=1),
    )

    assert result["passed"] is True


def test_panel_evaluation_evidence_uses_latest_symbol_time_per_row() -> None:
    index = pd.date_range("2024-01-01", periods=5, freq="D")
    prediction_times = pd.DataFrame({"AAA": index, "BBB": index}, index=index)
    evaluation_times = pd.DataFrame(
        {
            "AAA": index + pd.Timedelta(days=1),
            "BBB": index + pd.Timedelta(days=3),
        },
        index=index,
    )

    pred_times, eval_times, metadata = _row_level_prediction_evaluation_times(
        index,
        LabelEvaluationEvidence(
            prediction_times=prediction_times,
            evaluation_times=evaluation_times,
            metadata={},
        ),
    )

    assert pred_times.loc[index[0]] == index[0]
    assert eval_times.loc[index[0]] == index[0] + pd.Timedelta(days=3)
    assert metadata["panel_policy"] == "latest_evaluation_time_across_selected_symbols"


def _fixlb_config(n: int) -> LabelConfig:
    return LabelConfig(
        generator=LabelGeneratorConfig(kind="fixlb", params={"n": n}),
        target=LabelTargetConfig(
            transform=LabelTargetTransformConfig(
                name="threshold_future_return",
                params={"threshold": 0.0},
            )
        ),
    )


def _pivot_config() -> LabelConfig:
    return LabelConfig(
        generator=LabelGeneratorConfig(kind="pivotlb", params={"up_th": 0.2, "down_th": 0.2}),
        target=LabelTargetConfig(
            transform=LabelTargetTransformConfig(
                name="positive_event",
                params={"positive_value": -1},
            )
        ),
    )
