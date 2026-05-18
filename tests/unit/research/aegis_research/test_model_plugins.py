from __future__ import annotations

from research.aegis_research.config import load_experiment_config
from research.aegis_research.model_plugins import (
    SKLEARN_LOGISTIC_PLUGIN_ID,
    make_default_model_registry,
)
from tests.support.research.aegis_research.experiment_config_fixtures import (
    SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG,
)


def test_default_model_registry_contains_sklearn_logistic_plugin() -> None:
    registry = make_default_model_registry()

    assert SKLEARN_LOGISTIC_PLUGIN_ID in registry
    definition = registry.get(SKLEARN_LOGISTIC_PLUGIN_ID)
    assert definition.declaration.version == "1.0.0"
    assert "positive_class_probability" in definition.declaration.prediction_outputs


def test_scaffold_fixture_config_resolves_against_default_model_registry() -> None:
    registry = make_default_model_registry()

    resolved = load_experiment_config(
        SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG,
        model_registry=registry,
    )

    assert resolved.config.model.plugin_id == SKLEARN_LOGISTIC_PLUGIN_ID
