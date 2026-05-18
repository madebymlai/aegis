from __future__ import annotations

from research.aegis_research.model_plugins.sklearn_logistic import (
    SKLEARN_LOGISTIC_PLUGIN_ID,
    SklearnLogisticPlugin,
    sklearn_logistic_definition,
)
from research.aegis_research.model_registry import FrozenModelRegistry, ModelRegistry


def make_default_model_registry() -> FrozenModelRegistry:
    registry = ModelRegistry()
    registry.register(sklearn_logistic_definition())
    return registry.freeze()


__all__ = [
    "SKLEARN_LOGISTIC_PLUGIN_ID",
    "SklearnLogisticPlugin",
    "make_default_model_registry",
    "sklearn_logistic_definition",
]
