from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd

POSITIVE_CLASS_PROBABILITY = "positive_class_probability"


@dataclass(frozen=True)
class ModelPluginDeclaration:
    id: str
    version: str
    supported_target_roles: tuple[str, ...] = ("supervised_target",)
    supported_target_kinds: tuple[str, ...] = ("binary_classification",)
    prediction_outputs: tuple[str, ...] = (POSITIVE_CLASS_PROBABILITY,)
    state_schema_version: str = "model_state.v1"
    trusted_loading: bool = True
    package_versions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelExecutionContext:
    plugin_id: str
    split_label: str
    set_name: str
    target_schema: Mapping[str, Any]
    feature_columns: tuple[str, ...]


@dataclass(frozen=True)
class ModelDataset:
    features: pd.DataFrame
    target: pd.Series | None
    row_index: pd.MultiIndex
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelFitResult:
    state: Any
    observed_classes: tuple[Any, ...]
    class_probability_columns: Mapping[Any, str]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    state_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelPredictionResult:
    probabilities: pd.Series | pd.DataFrame
    observed_classes: tuple[Any, ...]
    class_probability_columns: Mapping[Any, str]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


class ModelPlugin(Protocol):
    def fit(
        self,
        dataset: ModelDataset,
        *,
        params: Mapping[str, Any],
        context: ModelExecutionContext,
    ) -> ModelFitResult: ...

    def predict(
        self,
        state: Any,
        dataset: ModelDataset,
        *,
        params: Mapping[str, Any],
        context: ModelExecutionContext,
    ) -> ModelPredictionResult: ...


ParamValidator = Callable[[Mapping[str, Any]], Mapping[str, str]]


@dataclass(frozen=True)
class ModelPluginDefinition:
    declaration: ModelPluginDeclaration
    plugin: ModelPlugin
    validate_params: ParamValidator | None = None
