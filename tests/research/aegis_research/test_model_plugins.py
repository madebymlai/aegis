from __future__ import annotations

from research.aegis_research.config import load_experiment_config
from research.aegis_research.model_plugins import (
    SKLEARN_LOGISTIC_PLUGIN_ID,
    make_default_model_registry,
)


def test_default_model_registry_contains_sklearn_logistic_plugin() -> None:
    registry = make_default_model_registry()

    assert SKLEARN_LOGISTIC_PLUGIN_ID in registry
    definition = registry.get(SKLEARN_LOGISTIC_PLUGIN_ID)
    assert definition.declaration.version == "1.0.0"
    assert "positive_class_probability" in definition.declaration.prediction_outputs


def test_baseline_config_resolves_against_default_model_registry() -> None:
    registry = make_default_model_registry()

    resolved = load_experiment_config(
        "research/configs/experiments/synthetic_purged_fixlb_baseline.yaml",
        model_registry=registry,
    )

    assert resolved.config.model.plugin_id == SKLEARN_LOGISTIC_PLUGIN_ID
