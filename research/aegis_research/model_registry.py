from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from research.aegis_research.model_contracts import (
    POSITIVE_CLASS_PROBABILITY,
    ModelPluginDefinition,
)


class ModelRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class FrozenModelRegistry:
    definitions: Mapping[str, ModelPluginDefinition]
    fingerprint: str

    def get(self, plugin_id: str) -> ModelPluginDefinition:
        try:
            return self.definitions[plugin_id]
        except KeyError as error:
            raise ModelRegistryError(f"unknown model plugin id: {plugin_id}") from error

    def __contains__(self, plugin_id: str) -> bool:
        return plugin_id in self.definitions


class ModelRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ModelPluginDefinition] = {}

    def register(self, definition: ModelPluginDefinition) -> None:
        _validate_definition(definition)
        plugin_id = definition.declaration.id
        if plugin_id in self._definitions:
            raise ModelRegistryError(f"duplicate model plugin id: {plugin_id}")
        self._definitions[plugin_id] = definition

    def freeze(self) -> FrozenModelRegistry:
        definitions = dict(self._definitions)
        return FrozenModelRegistry(
            definitions=MappingProxyType(definitions),
            fingerprint=_registry_fingerprint(definitions),
        )


def empty_model_registry() -> ModelRegistry:
    return ModelRegistry()


def freeze_model_registry(
    registry: ModelRegistry | FrozenModelRegistry | None,
) -> FrozenModelRegistry | None:
    if registry is None:
        return None
    if isinstance(registry, FrozenModelRegistry):
        return registry
    return registry.freeze()


def _validate_definition(definition: ModelPluginDefinition) -> None:
    declaration = definition.declaration
    if not declaration.id:
        raise ModelRegistryError("model plugin id must be non-empty")
    if not declaration.version:
        raise ModelRegistryError(f"model plugin {declaration.id} version must be non-empty")
    if POSITIVE_CLASS_PROBABILITY not in declaration.prediction_outputs:
        raise ModelRegistryError(
            f"model plugin {declaration.id} must declare {POSITIVE_CLASS_PROBABILITY} output"
        )
    if "binary_classification" not in declaration.supported_target_kinds:
        raise ModelRegistryError(
            f"model plugin {declaration.id} must support binary_classification targets"
        )


def _registry_fingerprint(definitions: Mapping[str, ModelPluginDefinition]) -> str:
    payload = {
        plugin_id: {
            "declaration": asdict(definition.declaration),
            "factory": _plugin_identity(definition.plugin),
        }
        for plugin_id, definition in sorted(definitions.items())
    }
    data = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _plugin_identity(plugin: Any) -> dict[str, Any]:
    plugin_type = type(plugin)
    identity: dict[str, Any] = {
        "module": plugin_type.__module__,
        "qualname": plugin_type.__qualname__,
    }
    try:
        source_name = inspect.getsourcefile(plugin_type)
    except TypeError:
        return identity
    if not source_name:
        return identity
    source_path = Path(source_name)
    if source_path.is_file():
        identity["source_hash"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    return identity
