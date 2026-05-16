from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from research.aegis_research.config import ModelConfig


def train_model(indicators: pd.DataFrame, labels: pd.Series, config: ModelConfig) -> Pipeline:
    dataset = pd.concat([indicators, labels], axis=1).dropna()
    if len(dataset) < config.min_train_samples:
        raise ValueError(
            f"Need at least {config.min_train_samples} train samples, got {len(dataset)}"
        )
    if config.kind != "logistic_regression":
        raise ValueError(f"Unsupported model kind: {config.kind}")
    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=1000, random_state=42)),
        ]
    )
    model.fit(dataset.drop(columns=[labels.name]), dataset[labels.name].astype(int))
    return model


def predict_long_probability(model: Pipeline, indicators: pd.DataFrame) -> pd.Series:
    usable = indicators.dropna()
    probabilities = pd.Series(index=indicators.index, dtype=float, name="long_probability")
    probabilities.loc[usable.index] = model.predict_proba(usable)[:, 1]
    return probabilities


def export_model(model: Pipeline, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
