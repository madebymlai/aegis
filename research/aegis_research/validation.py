from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from research.aegis_research.config import ExperimentConfig
from research.aegis_research.models import predict_long_probability, train_model
from research.aegis_research.portfolios import simulate_portfolio
from research.aegis_research.reports import portfolio_metrics
from research.aegis_research.signals import probabilities_to_signals
from research.aegis_research.splits import ValidationSplit


@dataclass(frozen=True)
class ValidationResult:
    model: Any
    probabilities: pd.Series | pd.DataFrame
    entries: pd.Series | pd.DataFrame
    exits: pd.Series | pd.DataFrame
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    split_metrics: pd.DataFrame
    validation_metadata: dict[str, Any]


def evaluate_validation_splits(
    close: pd.Series,
    indicators: pd.DataFrame,
    labels: pd.Series,
    splits: list[ValidationSplit],
    config: ExperimentConfig,
) -> ValidationResult:
    if not splits:
        raise ValueError("At least one validation split is required")

    split_rows: list[dict[str, Any]] = []
    probability_columns: dict[str, pd.Series] = {}
    entry_columns: dict[str, pd.Series] = {}
    exit_columns: dict[str, pd.Series] = {}
    last_model: Any = None

    for split in splits:
        train_indicators = indicators.loc[split.train_index]
        train_labels = labels.loc[split.train_index]
        model = train_model(train_indicators, train_labels, config.model)
        probabilities = predict_long_probability(model, indicators.loc[split.train_index.union(split.test_index)])
        entries, exits = probabilities_to_signals(probabilities, config.signals)

        train_pf = simulate_portfolio(
            close.loc[split.train_index],
            entries.loc[split.train_index],
            exits.loc[split.train_index],
            config.portfolio,
        )
        test_pf = simulate_portfolio(
            close.loc[split.test_index],
            entries.loc[split.test_index],
            exits.loc[split.test_index],
            config.portfolio,
        )

        train_metrics = portfolio_metrics(train_pf)
        test_metrics = portfolio_metrics(test_pf)
        split_rows.extend(
            [
                {"split": split.label, "set": "train", **train_metrics},
                {"split": split.label, "set": "test", **test_metrics},
            ]
        )
        probability_columns[split.label] = probabilities
        entry_columns[split.label] = entries
        exit_columns[split.label] = exits
        last_model = model

    split_metrics = pd.DataFrame(split_rows).set_index(["split", "set"])
    train_metrics = _aggregate_metrics(split_metrics.xs("train", level="set"))
    test_metrics = _aggregate_metrics(split_metrics.xs("test", level="set"))
    probabilities_df = pd.DataFrame(probability_columns)
    entries_df = pd.DataFrame(entry_columns).astype("boolean").fillna(False).astype(bool)
    exits_df = pd.DataFrame(exit_columns).astype("boolean").fillna(False).astype(bool)

    return ValidationResult(
        model=last_model,
        probabilities=_squeeze_single_column(probabilities_df),
        entries=_squeeze_single_column(entries_df),
        exits=_squeeze_single_column(exits_df),
        train_metrics=train_metrics,
        test_metrics=test_metrics,
        split_metrics=split_metrics,
        validation_metadata={
            "kind": config.split.kind,
            "n_splits": len(splits),
        },
    )


def _aggregate_metrics(metrics: pd.DataFrame) -> dict[str, Any]:
    return {
        "total_return_pct": metrics["total_return_pct"].mean(),
        "sharpe_ratio": metrics["sharpe_ratio"].mean(),
        "max_drawdown_pct": metrics["max_drawdown_pct"].max(),
        "total_trades": metrics["total_trades"].sum(),
        "win_rate_pct": metrics["win_rate_pct"].mean(),
        "total_fees_paid": metrics["total_fees_paid"].sum(),
    }


def _squeeze_single_column(frame: pd.DataFrame) -> pd.Series | pd.DataFrame:
    if len(frame.columns) == 1:
        return frame.iloc[:, 0]
    return frame
