from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from research.aegis_research.config import ExperimentConfig
from research.aegis_research.models import predict_long_probability, train_model
from research.aegis_research.portfolios import simulate_portfolio
from research.aegis_research.reports import portfolio_metrics
from research.aegis_research.signals import probabilities_to_signals
from research.aegis_research.splits import TrainTestSplit


@dataclass(frozen=True)
class ValidationResult:
    model: Any
    probabilities: pd.Series
    entries: pd.Series
    exits: pd.Series
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]


def evaluate_holdout_split(
    close: pd.Series,
    indicators: pd.DataFrame,
    labels: pd.Series,
    split: TrainTestSplit,
    config: ExperimentConfig,
) -> ValidationResult:
    train_indicators = indicators.loc[split.train_index]
    train_labels = labels.loc[split.train_index]

    model = train_model(train_indicators, train_labels, config.model)
    probabilities = predict_long_probability(model, indicators)
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

    return ValidationResult(
        model=model,
        probabilities=probabilities,
        entries=entries,
        exits=exits,
        train_metrics=portfolio_metrics(train_pf),
        test_metrics=portfolio_metrics(test_pf),
    )
