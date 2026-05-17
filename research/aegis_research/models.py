from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from research.aegis_research.config import ModelConfig
from research.aegis_research.splits import ValidationSplit

LABEL_COLUMN = "__label__"


class TargetModelCompatibilityError(ValueError):
    def __init__(self, diagnostics: dict[str, Any]) -> None:
        self.diagnostics = diagnostics
        super().__init__(str(diagnostics.get("failure_reason", "target/model incompatible")))


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


def target_model_compatibility(
    labels: pd.DataFrame,
    config: ModelConfig,
    target_schema: dict[str, Any],
    splits: list[ValidationSplit] | None = None,
    *,
    phase: str,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "phase": phase,
        "compatible": True,
        "target_kind": target_schema.get("target_kind"),
        "target_role": target_schema.get("target_role"),
        "model_kind": config.kind,
        "split_safety": target_schema.get("split_safety", {}),
        "splits": [],
        "failure_reason": None,
    }
    if config.kind != "logistic_regression":
        return _incompatible(diagnostics, f"Unsupported model kind: {config.kind}")
    if target_schema.get("target_role") != "supervised_target":
        return _incompatible(diagnostics, "current model requires target role 'supervised_target'")
    if target_schema.get("target_kind") != "binary_classification":
        return _incompatible(
            diagnostics,
            "current model requires binary classification target; broader target support belongs to #9",
        )
    if not isinstance(labels, pd.DataFrame) or isinstance(labels.columns, pd.MultiIndex):
        return _incompatible(diagnostics, "selected target must be a timestamp-by-symbol panel")

    if splits is None:
        return diagnostics

    for split in splits:
        values = labels.loc[split.train_index].stack().dropna().astype(int)
        class_counts = {str(key): int(value) for key, value in values.value_counts().items()}
        diagnostics["splits"].append({"label": split.label, "train_class_counts": class_counts})
        if len(class_counts) < 2:
            return _incompatible(
                diagnostics,
                f"Split {split.label} training target must contain both classes",
            )
    return diagnostics


def assert_target_model_compatible(diagnostics: dict[str, Any]) -> None:
    if not diagnostics.get("compatible", False):
        raise TargetModelCompatibilityError(diagnostics)


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
        if (
            isinstance(symbol_features.columns, pd.MultiIndex)
            and "feature" in symbol_features.columns.names
        ):
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


def _incompatible(diagnostics: dict[str, Any], reason: str) -> dict[str, Any]:
    return {**diagnostics, "compatible": False, "failure_reason": reason}
