from __future__ import annotations

from research.aegis_research.model_contracts import ModelPluginDeclaration, ModelPluginDefinition
from research.aegis_research.model_plugins import (
    SKLEARN_LOGISTIC_PLUGIN_ID,
    SklearnLogisticPlugin,
    make_default_model_registry,
)
from research.aegis_research.model_registry import ModelRegistry, _plugin_identity
from tests.support.research.aegis_research.experiment_config_fixtures import (
    SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG,
    load_train_fixture_config,
)


def test_default_model_registry_contains_sklearn_logistic_plugin() -> None:
    registry = make_default_model_registry()

    assert SKLEARN_LOGISTIC_PLUGIN_ID in registry
    definition = registry.get(SKLEARN_LOGISTIC_PLUGIN_ID)
    assert definition.declaration.version == "1.0.0"
    assert "positive_class_probability" in definition.declaration.prediction_outputs


def test_scaffold_fixture_config_resolves_against_default_model_registry() -> None:
    registry = make_default_model_registry()

    resolved = load_train_fixture_config(
        SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG,
        model_registry=registry,
    )

    assert resolved.config.model.plugin_id == SKLEARN_LOGISTIC_PLUGIN_ID


def test_model_registry_fingerprint_records_unavailable_plugin_source(monkeypatch) -> None:
    def raise_source_error(_plugin_type):
        raise OSError("source code not available")

    plugin = SklearnLogisticPlugin()
    monkeypatch.setattr(
        "research.aegis_research.model_registry.inspect.getsourcefile",
        raise_source_error,
    )

    identity = _plugin_identity(plugin)

    assert identity["source_unavailable_reason"] == "OSError"
    assert "source_hash" not in identity

    registry = ModelRegistry()
    registry.register(
        ModelPluginDefinition(
            declaration=ModelPluginDeclaration(id="examples.inline", version="1.0.0"),
            plugin=plugin,
        )
    )

    assert len(registry.freeze().fingerprint) == 64
