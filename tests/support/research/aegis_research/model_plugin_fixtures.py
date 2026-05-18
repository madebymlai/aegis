from __future__ import annotations

from typing import Any

from research.aegis_research.model_plugins import (
    SKLEARN_LOGISTIC_PLUGIN_ID,
    SklearnLogisticPlugin,
    make_default_model_registry,
)
from research.aegis_research.model_registry import FrozenModelRegistry

SklearnLogisticTestPlugin = SklearnLogisticPlugin


def make_model_registry() -> FrozenModelRegistry:
    return make_default_model_registry()


def model_config_dict(min_train_samples: int = 1) -> dict[str, Any]:
    return {
        "plugin_id": SKLEARN_LOGISTIC_PLUGIN_ID,
        "min_train_samples": min_train_samples,
        "params": {"max_iter": 1000, "random_state": 42},
    }
