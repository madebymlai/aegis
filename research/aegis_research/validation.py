from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from research.aegis_research.config import ExperimentConfig
from research.aegis_research.data_schema import index_identity
from research.aegis_research.model_registry import FrozenModelRegistry
from research.aegis_research.models import (
    TrainedModel,
    predict_positive_class_probability,
    train_model,
)
from research.aegis_research.portfolios import simulate_portfolio
from research.aegis_research.reports import portfolio_metrics
from research.aegis_research.signals import probabilities_to_signals
from research.aegis_research.splits import ValidationSplit, split_purging_passed


@dataclass(frozen=True)
class SplitValidationResult:
    label: str
    model: TrainedModel
    train_probabilities: pd.DataFrame
    test_probabilities: pd.DataFrame
    train_entries: pd.DataFrame
    test_entries: pd.DataFrame
    train_exits: pd.DataFrame
    test_exits: pd.DataFrame
    train_portfolio: Any
    test_portfolio: Any
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ValidationResult:
    split_results: list[SplitValidationResult]
    probabilities: pd.DataFrame
    entries: pd.DataFrame
    exits: pd.DataFrame
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    split_metrics: pd.DataFrame
    validation_metadata: dict[str, Any]

    @property
    def model(self) -> Any:
        return self.split_results[-1].model


def evaluate_validation_splits(
    close: pd.DataFrame,
    indicators: pd.DataFrame,
    labels: pd.DataFrame,
    splits: list[ValidationSplit],
    config: ExperimentConfig,
    *,
    target_schema: dict[str, Any],
    split_metadata: dict[str, Any] | None = None,
    compatibility: dict[str, Any] | None = None,
    model_registry: FrozenModelRegistry | None = None,
    on_split_result: Callable[[SplitValidationResult], None] | None = None,
) -> ValidationResult:
    if not splits:
        raise ValueError("At least one validation split is required")
    if not target_schema:
        raise ValueError("target_schema is required for model plugin validation")
    split_metadata = split_metadata or {}
    compatibility = compatibility or {}

    split_rows: list[dict[str, Any]] = []
    probability_frames: dict[str, pd.DataFrame] = {}
    entry_frames: dict[str, pd.DataFrame] = {}
    exit_frames: dict[str, pd.DataFrame] = {}
    split_results: list[SplitValidationResult] = []

    for split in splits:
        train_indicators = indicators.loc[split.train_index]
        train_labels = labels.loc[split.train_index]
        model = train_model(
            train_indicators,
            train_labels,
            config.model,
            model_registry=model_registry,
            target_schema=target_schema,
            split_label=split.label,
        )
        probabilities = predict_positive_class_probability(
            model,
            indicators.loc[split.train_index.union(split.test_index)],
            target_schema=target_schema,
            split_label=split.label,
            set_name="validation_union",
        )
        entries, exits = probabilities_to_signals(probabilities, config.signals)
        train_close = close.loc[split.train_index]
        test_close = close.loc[split.test_index]
        train_probabilities = probabilities.loc[split.train_index]
        test_probabilities = probabilities.loc[split.test_index]
        train_entries = entries.loc[split.train_index]
        test_entries = entries.loc[split.test_index]
        train_exits = exits.loc[split.train_index]
        test_exits = exits.loc[split.test_index]

        train_pf = simulate_portfolio(
            train_close,
            train_entries,
            train_exits,
            config.portfolio,
        )
        test_pf = simulate_portfolio(
            test_close,
            test_entries,
            test_exits,
            config.portfolio,
        )

        train_metrics = portfolio_metrics(train_pf, config.report)
        test_metrics = portfolio_metrics(test_pf, config.report)
        split_rows.extend(
            [
                {"split": split.label, "set": "train", **train_metrics},
                {"split": split.label, "set": "test", **test_metrics},
            ]
        )
        probability_frames[split.label] = test_probabilities
        entry_frames[split.label] = test_entries
        exit_frames[split.label] = test_exits
        split_result = SplitValidationResult(
            label=split.label,
            model=model,
            train_probabilities=train_probabilities,
            test_probabilities=test_probabilities,
            train_entries=train_entries,
            test_entries=test_entries,
            train_exits=train_exits,
            test_exits=test_exits,
            train_portfolio=train_pf,
            test_portfolio=test_pf,
            train_metrics=train_metrics,
            test_metrics=test_metrics,
            metadata={
                "label": split.label,
                "target": target_schema,
                "model": model.metadata,
                "probabilities": {
                    "train": _probability_diagnostics(train_probabilities),
                    "test": _probability_diagnostics(test_probabilities),
                },
                "compatibility": compatibility,
                "sets": {
                    "train": {"rows": len(split.train_index), **index_identity(split.train_index)},
                    "test": {"rows": len(split.test_index), **index_identity(split.test_index)},
                },
            },
        )
        split_results.append(split_result)
        if on_split_result is not None:
            on_split_result(split_result)

    split_metrics = pd.DataFrame(split_rows).set_index(["split", "set"])
    train_metrics = _aggregate_metrics(split_metrics.xs("train", level="set"))
    test_metrics = _aggregate_metrics(split_metrics.xs("test", level="set"))
    probabilities = _concat_split_frames(probability_frames)
    entries = _concat_split_frames(entry_frames).astype("boolean").fillna(False).astype(bool)
    exits = _concat_split_frames(exit_frames).astype("boolean").fillna(False).astype(bool)

    return ValidationResult(
        split_results=split_results,
        probabilities=probabilities,
        entries=entries,
        exits=exits,
        train_metrics=train_metrics,
        test_metrics=test_metrics,
        split_metrics=split_metrics,
        validation_metadata={
            "kind": config.split.kind,
            "n_splits": len(splits),
            "target": target_schema,
            "split_metadata": split_metadata,
            "compatibility": compatibility,
            "decision_grade": _decision_grade(
                target_schema,
                split_metadata=split_metadata,
                compatibility=compatibility,
            ),
            "decision_grade_scope": "label_window_purging",
            "feature_causality_checked": False,
            "portfolio_execution_timing_checked": False,
            "decision_evidence": "per_split_test_metrics",
            "probability_output_name": "positive_class_probability",
            "probability_calibrated": False,
            "aggregate_metrics_role": "descriptive_summary",
            "aggregation_methods": _aggregation_methods(),
        },
    )


def _aggregate_metrics(metrics: pd.DataFrame) -> dict[str, Any]:
    def numeric_column(name: str) -> pd.Series:
        return pd.to_numeric(metrics[name], errors="coerce").dropna()

    total_return = numeric_column("total_return_pct")
    sharpe = numeric_column("sharpe_ratio")
    max_drawdown = numeric_column("max_drawdown_pct")
    trades = numeric_column("total_trades")
    win_rate = numeric_column("win_rate_pct")
    fees = numeric_column("total_fees_paid")
    aggregated = {
        "total_return_pct": total_return.mean() if len(total_return) else None,
        "sharpe_ratio": sharpe.mean() if len(sharpe) else None,
        "max_drawdown_pct": max_drawdown.max() if len(max_drawdown) else None,
        "total_trades": trades.sum() if len(trades) else None,
        "win_rate_pct": win_rate.mean() if len(win_rate) else None,
        "total_fees_paid": fees.sum() if len(fees) else None,
    }
    if "per_symbol" in metrics:
        aggregated["per_symbol"] = _aggregate_per_symbol_metrics(metrics["per_symbol"])
    return aggregated


def _probability_diagnostics(probabilities: pd.DataFrame) -> dict[str, Any]:
    values = probabilities.stack().dropna()
    return {
        "rows": len(probabilities),
        "symbols": [str(column) for column in probabilities.columns],
        "observations": int(values.size),
        "missing": int(probabilities.isna().sum().sum()),
        "min": float(values.min()) if len(values) else None,
        "max": float(values.max()) if len(values) else None,
        "mean": float(values.mean()) if len(values) else None,
    }


def _aggregate_per_symbol_metrics(rows: pd.Series) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, list[float]]] = {}
    for row in rows.dropna():
        for metric_name, metric_values in row.items():
            metric = values.setdefault(metric_name, {})
            for symbol, value in metric_values.items():
                if value is not None:
                    metric.setdefault(symbol, []).append(float(value))

    return {
        metric_name: {
            symbol: _aggregate_symbol_values(metric_name, symbol_values)
            for symbol, symbol_values in metric_values.items()
        }
        for metric_name, metric_values in values.items()
    }


def _aggregate_symbol_values(metric_name: str, values: list[float]) -> Any:
    if not values:
        return None
    if metric_name in {"total_trades", "total_fees_paid"}:
        return sum(values)
    if metric_name == "max_drawdown_pct":
        return max(values)
    return sum(values) / len(values)


def _concat_split_frames(
    frames: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def _decision_grade(
    target_schema: dict[str, Any] | None,
    *,
    split_metadata: dict[str, Any] | None,
    compatibility: dict[str, Any] | None,
) -> bool:
    if compatibility and not compatibility.get("compatible", False):
        return False
    if not target_schema:
        return False
    split_safety = target_schema.get("split_safety", {})
    if not split_safety.get("purging_required"):
        return True
    return split_purging_passed(split_metadata)


def _aggregation_methods() -> dict[str, str]:
    return {
        "total_return_pct": "mean_across_splits",
        "sharpe_ratio": "mean_across_splits",
        "max_drawdown_pct": "max_across_splits",
        "total_trades": "sum_across_splits",
        "win_rate_pct": "mean_across_splits",
        "total_fees_paid": "sum_across_splits",
        "per_symbol": "metric_specific_across_splits",
    }
