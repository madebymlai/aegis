from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from research.aegis_research.config import ModelConfig

LABEL_COLUMN = "__label__"


def train_model(
    indicators: pd.DataFrame,
    labels: pd.DataFrame,
    config: ModelConfig,
) -> Pipeline:
    dataset = _training_dataset(indicators, labels)
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
    model.fit(dataset.drop(columns=[LABEL_COLUMN]), dataset[LABEL_COLUMN].astype(int))
    return model


def predict_long_probability(
    model: Pipeline,
    indicators: pd.DataFrame,
) -> pd.DataFrame:
    stacked = _stack_indicator_panel(indicators)
    usable = stacked.dropna()
    probabilities = pd.Series(index=stacked.index, dtype=float, name="long_probability")
    probabilities.loc[usable.index] = model.predict_proba(usable)[:, 1]
    return probabilities.unstack("symbol").reindex(index=indicators.index)


def export_model(model: Pipeline, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def _training_dataset(
    indicators: pd.DataFrame,
    labels: pd.DataFrame,
) -> pd.DataFrame:
    _validate_feature_label_symbols(indicators, labels)
    features = _stack_indicator_panel(indicators, symbols=labels.columns)
    label_values = _stack_label_panel(labels)
    return features.join(label_values.rename(LABEL_COLUMN)).dropna()


def _stack_indicator_panel(
    indicators: pd.DataFrame,
    *,
    symbols: pd.Index | None = None,
) -> pd.DataFrame:
    if not _has_symbol_level(indicators):
        raise ValueError("indicator columns must include a symbol level")

    symbol_level = indicators.columns.names.index("symbol")
    if symbols is None:
        symbols = indicators.columns.get_level_values(symbol_level).unique()
    available_symbols = set(indicators.columns.get_level_values(symbol_level))
    missing_symbols = [symbol for symbol in symbols if symbol not in available_symbols]
    if missing_symbols:
        raise ValueError(f"indicator features are missing symbols: {missing_symbols}")

    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        symbol_features = indicators.xs(symbol, axis=1, level="symbol", drop_level=True)
        symbol_features = symbol_features.copy()
        if isinstance(symbol_features.columns, pd.MultiIndex) and "feature" in symbol_features.columns.names:
            symbol_features.columns = symbol_features.columns.get_level_values("feature")
        else:
            symbol_features.columns = [
                "__".join(map(str, column)) if isinstance(column, tuple) else str(column)
                for column in symbol_features.columns
            ]
        if symbol_features.columns.duplicated().any():
            duplicates = sorted(set(symbol_features.columns[symbol_features.columns.duplicated()]))
            raise ValueError(f"indicator feature names collide: {duplicates}")
        symbol_features.index = pd.MultiIndex.from_arrays(
            [symbol_features.index, [symbol] * len(symbol_features)],
            names=[indicators.index.name, "symbol"],
        )
        frames.append(symbol_features)
    return pd.concat(frames).sort_index()


def _stack_label_panel(labels: pd.DataFrame) -> pd.Series:
    stacked = labels.stack()
    stacked.index = stacked.index.set_names([labels.index.name, "symbol"])
    return stacked


def _has_symbol_level(indicators: pd.DataFrame) -> bool:
    return isinstance(indicators.columns, pd.MultiIndex) and "symbol" in indicators.columns.names


def _validate_feature_label_symbols(indicators: pd.DataFrame, labels: pd.DataFrame) -> None:
    if not _has_symbol_level(indicators):
        raise ValueError("indicator columns must include a symbol level")
    symbol_level = indicators.columns.names.index("symbol")
    feature_symbols = set(map(str, indicators.columns.get_level_values(symbol_level)))
    label_symbols = set(map(str, labels.columns))
    if feature_symbols != label_symbols:
        raise ValueError(
            "indicator feature symbols must match labels: "
            f"features={sorted(feature_symbols)}, labels={sorted(label_symbols)}"
        )
