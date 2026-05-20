from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import SplitConfig
from research.aegis_research.data_schema import index_identity
from research.aegis_research.labels import LabelEvaluationEvidence


@dataclass(frozen=True)
class ValidationSplit:
    label: str
    train_index: pd.Index
    test_index: pd.Index


@dataclass(frozen=True)
class ValidationSplitsResult:
    splits: list[ValidationSplit]
    metadata: dict[str, Any]
    native_object: Any | None = None


def build_validation_splits(
    index: pd.Index,
    config: SplitConfig,
    *,
    target_metadata: dict[str, Any] | None = None,
    evaluation_evidence: LabelEvaluationEvidence | None = None,
) -> list[ValidationSplit]:
    return build_validation_splits_result(
        index,
        config,
        target_metadata=target_metadata,
        evaluation_evidence=evaluation_evidence,
    ).splits


def build_validation_splits_result(
    index: pd.Index,
    config: SplitConfig,
    *,
    target_metadata: dict[str, Any] | None = None,
    evaluation_evidence: LabelEvaluationEvidence | None = None,
) -> ValidationSplitsResult:
    if config.kind == "purged_kfold":
        return _purged_kfold_splits_result(
            index,
            config,
            target_metadata=target_metadata,
            evaluation_evidence=evaluation_evidence,
        )
    raise ValueError(f"Unsupported split kind: {config.kind}")


def _purged_kfold_splits_result(
    index: pd.Index,
    config: SplitConfig,
    *,
    target_metadata: dict[str, Any] | None,
    evaluation_evidence: LabelEvaluationEvidence | None,
) -> ValidationSplitsResult:
    if evaluation_evidence is None:
        raise ValueError("purged_kfold requires label evaluation evidence")

    pred_times, eval_times, time_validation = _row_level_prediction_evaluation_times(
        index,
        evaluation_evidence,
    )
    split_count = _purged_split_count(config)
    if split_count > config.max_splits:
        raise ValueError(
            f"purged_kfold would create {split_count} splits, exceeding split.max_splits"
        )

    purge_td = pd.Timedelta(config.purge_td)
    embargo_td = pd.Timedelta(config.embargo_td)
    splitter = vbt.Splitter.from_purged_kfold(
        index,
        n_folds=config.n_folds,
        n_test_folds=config.n_test_folds,
        purge_td=purge_td,
        embargo_td=embargo_td,
        pred_times=pred_times,
        eval_times=eval_times,
    )
    splits = _validation_splits_from_index_slices(splitter.take(index))
    resource_estimate = _resource_estimate(
        index,
        splits,
        max_public_artifact_bytes=config.max_public_artifact_bytes,
    )
    if resource_estimate["estimated_output_cells"] > config.max_estimated_output_cells:
        raise ValueError(
            "purged_kfold estimated output cells exceed split.max_estimated_output_cells"
        )

    leakage_invariant = _assert_no_interval_leakage(
        splits,
        pred_times,
        eval_times,
        purge_td=purge_td,
        embargo_td=embargo_td,
    )

    metadata = _split_metadata(config, index, splits, target_metadata=target_metadata)
    metadata.update(
        {
            "purging_applied": True,
            "purge_td": str(purge_td),
            "embargo_td": str(embargo_td),
            "n_folds": config.n_folds,
            "n_test_folds": config.n_test_folds,
            "time_validation": time_validation,
            "leakage_invariant": leakage_invariant,
            "resource_estimate": resource_estimate,
            "sample_intervals": _sample_interval_metadata(index, pred_times, eval_times),
        }
    )
    return ValidationSplitsResult(splits=splits, metadata=metadata, native_object=splitter)


def _validation_splits_from_index_slices(
    index_slices: Any,
) -> list[ValidationSplit]:
    splits: list[ValidationSplit] = []
    for split_label in index_slices.index.get_level_values("split").unique():
        train_index = index_slices.loc[(split_label, "train")]
        test_index = index_slices.loc[(split_label, "test")]
        if len(train_index) == 0 or len(test_index) == 0:
            raise ValueError(f"Split {split_label} produced an empty train or test range")
        splits.append(
            ValidationSplit(
                label=f"split_{split_label}",
                train_index=train_index,
                test_index=test_index,
            )
        )
    return splits


def split_purging_passed(split_metadata: dict[str, Any] | None) -> bool:
    if not split_metadata or not split_metadata.get("purging_applied"):
        return False
    leakage_invariant = split_metadata.get("leakage_invariant", {})
    return leakage_invariant.get("passed") is True


def _split_metadata(
    config: SplitConfig,
    index: pd.Index,
    splits: list[ValidationSplit],
    *,
    target_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "kind": config.kind,
        "n_splits": len(splits),
        "source_index": index_identity(index),
        "sample_intervals": [],
        "splits": _split_membership_metadata(index, splits),
    }
    if target_metadata is not None:
        metadata["target"] = target_metadata
    return metadata


def _row_level_prediction_evaluation_times(
    index: pd.Index,
    evidence: LabelEvaluationEvidence,
) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    pred_frame = evidence.prediction_times.reindex(index)
    eval_frame = evidence.evaluation_times.reindex(index)
    if pred_frame.isna().any().any():
        raise ValueError("purged_kfold requires prediction time for every selected target row")
    if eval_frame.isna().any().any():
        raise ValueError("purged_kfold requires evaluation time for every selected target row")

    pred_times = pred_frame.max(axis=1).rename("pred_time")
    eval_times = eval_frame.max(axis=1).rename("eval_time")
    _validate_prediction_evaluation_times(index, pred_times, eval_times)
    return (
        pred_times,
        eval_times,
        {
            "pred_times_explicit": True,
            "eval_times_explicit": True,
            "panel_policy": "latest_evaluation_time_across_selected_symbols",
            "sample_grain": "timestamp_symbol_targets_projected_to_row_membership",
        },
    )


def _validate_prediction_evaluation_times(
    index: pd.Index,
    pred_times: pd.Series,
    eval_times: pd.Series,
) -> None:
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("purged_kfold requires a datetime-like index")
    if not index.is_unique:
        raise ValueError("purged_kfold requires a unique datetime-like index")
    if not index.is_monotonic_increasing:
        raise ValueError("purged_kfold requires a monotonic datetime-like index")
    if not pred_times.index.equals(index) or not eval_times.index.equals(index):
        raise ValueError("purged_kfold prediction/evaluation times must align to the split index")
    if not pd.api.types.is_datetime64_any_dtype(pred_times):
        raise ValueError("purged_kfold prediction times must be datetime-like")
    if not pd.api.types.is_datetime64_any_dtype(eval_times):
        raise ValueError("purged_kfold evaluation times must be datetime-like")
    if getattr(pred_times.dtype, "tz", None) != getattr(eval_times.dtype, "tz", None):
        raise ValueError("purged_kfold prediction/evaluation times must use the same timezone")
    if getattr(index.dtype, "tz", None) != getattr(pred_times.dtype, "tz", None):
        raise ValueError("purged_kfold index and prediction times must use the same timezone")
    if pred_times.isna().any() or eval_times.isna().any():
        raise ValueError("purged_kfold prediction/evaluation times must not contain NaT")
    if not pred_times.is_monotonic_increasing:
        raise ValueError("purged_kfold samples must be ordered by prediction time")
    if (eval_times < pred_times).any():
        raise ValueError(
            "purged_kfold evaluation times must be greater than or equal to prediction times"
        )


def _assert_no_interval_leakage(
    splits: list[ValidationSplit],
    pred_times: pd.Series,
    eval_times: pd.Series,
    *,
    purge_td: pd.Timedelta,
    embargo_td: pd.Timedelta,
) -> dict[str, Any]:
    for split in splits:
        test_pred = pred_times.loc[split.test_index].sort_values()
        test_eval_embargoed = (eval_times.loc[split.test_index] + embargo_td).sort_values()
        train_pred = pred_times.loc[split.train_index]
        train_eval = eval_times.loc[split.train_index] + purge_td

        test_start_count = pd.Index(test_pred).searchsorted(train_eval.to_numpy(), side="right")
        test_end_before_train = pd.Index(test_eval_embargoed).searchsorted(
            train_pred.to_numpy(),
            side="left",
        )
        unsafe = pd.Series(test_start_count > test_end_before_train, index=train_pred.index)
        if bool(unsafe.any()):
            first_train_label = unsafe.index[unsafe][0]
            overlapping_test = (test_pred <= train_eval.loc[first_train_label]) & (
                test_eval_embargoed >= train_pred.loc[first_train_label]
            )
            first_test_label = overlapping_test.index[overlapping_test][0]
            raise ValueError(
                "purged_kfold train interval overlaps test interval: "
                f"split={split.label}, train={first_train_label}, test={first_test_label}"
            )
    return {
        "passed": True,
        "method": "interval_boundary_search_disjoint_or_embargoed",
        "checked_splits": len(splits),
    }


def _purged_split_count(config: SplitConfig) -> int:
    from math import comb

    return comb(config.n_folds, config.n_test_folds)


def _resource_estimate(
    index: pd.Index,
    splits: list[ValidationSplit],
    *,
    max_public_artifact_bytes: int | None = None,
) -> dict[str, int]:
    total_membership_entries = sum(
        len(split.train_index) + len(split.test_index) for split in splits
    )
    estimate = {
        "split_count": len(splits),
        "source_rows": len(index),
        "total_membership_entries": total_membership_entries,
        "estimated_output_cells": total_membership_entries,
        "estimated_public_artifact_bytes": total_membership_entries * 16,
        "estimated_interval_checks": total_membership_entries,
    }
    if max_public_artifact_bytes is not None:
        estimate["max_public_artifact_bytes"] = max_public_artifact_bytes
    return estimate


def _sample_interval_metadata(
    source_index: pd.Index,
    pred_times: pd.Series,
    eval_times: pd.Series,
) -> list[dict[str, Any]]:
    return [
        {
            "position": position,
            "timestamp": _public_time_value(label),
            "prediction_time": _public_time_value(pred_times.loc[label]),
            "evaluation_time": _public_time_value(eval_times.loc[label]),
        }
        for position, label in enumerate(source_index)
    ]


def _split_membership_metadata(
    source_index: pd.Index,
    splits: list[ValidationSplit],
) -> list[dict[str, Any]]:
    return [
        {
            "label": split.label,
            "train": {
                **index_identity(split.train_index),
                "membership": _membership_representation(source_index, split.train_index),
            },
            "test": {
                **index_identity(split.test_index),
                "membership": _membership_representation(source_index, split.test_index),
            },
        }
        for split in splits
    ]


def _membership_representation(source_index: pd.Index, member_index: pd.Index) -> dict[str, Any]:
    positions = source_index.get_indexer(member_index)
    if (positions < 0).any():
        raise ValueError("split membership contains rows outside the source index")
    if len(positions) == 0:
        return {"kind": "empty", "positions": []}
    if len(positions) == 1 or bool(((positions[1:] - positions[:-1]) == 1).all()):
        return {"kind": "range", "start": int(positions[0]), "stop": int(positions[-1]) + 1}
    return {"kind": "sparse_indices", "positions": [int(position) for position in positions]}


def _public_time_value(value: Any) -> str | None:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
