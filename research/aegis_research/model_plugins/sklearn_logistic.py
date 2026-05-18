from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from research.aegis_research.model_contracts import (
    POSITIVE_CLASS_PROBABILITY,
    ModelDataset,
    ModelExecutionContext,
    ModelFitResult,
    ModelPluginDeclaration,
    ModelPluginDefinition,
    ModelPredictionResult,
)

SKLEARN_LOGISTIC_PLUGIN_ID = "aegis.sklearn_logistic"


class SklearnLogisticPlugin:
    def fit(
        self,
        dataset: ModelDataset,
        *,
        params: Mapping[str, Any],
        context: ModelExecutionContext,
    ) -> ModelFitResult:
        options = _model_options(params)
        model = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=options["max_iter"],
                        random_state=options["random_state"],
                    ),
                ),
            ]
        )
        target = dataset.target
        if target is None:
            raise ValueError("fit dataset target is required")
        model.fit(dataset.features, target.astype(int))
        classes = tuple(model.named_steps["classifier"].classes_)
        return ModelFitResult(
            state={"model": model},
            observed_classes=classes,
            class_probability_columns=_class_probability_columns(classes),
            diagnostics={"estimator": "sklearn.linear_model.LogisticRegression"},
            state_metadata={"state_format": "pickle", "trusted_loader": "joblib_or_pickle"},
        )

    def predict(
        self,
        state: Any,
        dataset: ModelDataset,
        *,
        params: Mapping[str, Any],
        context: ModelExecutionContext,
    ) -> ModelPredictionResult:
        model = state["model"]
        probabilities = model.predict_proba(dataset.features)
        classes = tuple(model.named_steps["classifier"].classes_)
        columns = _class_probability_columns(classes)
        return ModelPredictionResult(
            probabilities=pd.DataFrame(
                probabilities,
                index=dataset.row_index,
                columns=[columns[class_label] for class_label in classes],
            ),
            observed_classes=classes,
            class_probability_columns=columns,
        )


def sklearn_logistic_definition() -> ModelPluginDefinition:
    return ModelPluginDefinition(
        declaration=ModelPluginDeclaration(
            id=SKLEARN_LOGISTIC_PLUGIN_ID,
            version="1.0.0",
            prediction_outputs=(POSITIVE_CLASS_PROBABILITY,),
            state_schema_version="aegis_sklearn_logistic_state.v1",
            package_versions={"sklearn": sklearn.__version__},
        ),
        plugin=SklearnLogisticPlugin(),
        validate_params=validate_params,
    )


def validate_params(params: Mapping[str, Any]) -> Mapping[str, str]:
    issues: dict[str, str] = {}
    allowed = {"max_iter", "random_state"}
    for key in sorted(set(params) - allowed):
        issues[str(key)] = "unknown plugin parameter"

    max_iter = params.get("max_iter", 1000)
    if not isinstance(max_iter, int) or isinstance(max_iter, bool) or max_iter <= 0:
        issues["max_iter"] = "must be a positive integer"

    random_state = params.get("random_state", 42)
    if not isinstance(random_state, int) or isinstance(random_state, bool):
        issues["random_state"] = "must be an integer"

    return issues


def _model_options(params: Mapping[str, Any]) -> dict[str, int]:
    return {
        "max_iter": int(params.get("max_iter", 1000)),
        "random_state": int(params.get("random_state", 42)),
    }


def _class_probability_columns(classes: tuple[Any, ...]) -> dict[Any, str]:
    return {class_label: f"class_{class_label}_probability" for class_label in classes}
