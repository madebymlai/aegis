from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from research.aegis_research.component_registry.contracts import (
    COMPONENT_FAMILIES,
    ComponentDefinition,
    ComponentFamily,
    ComponentRegistryError,
    ComponentSelection,
)
from research.aegis_research.component_registry.manifests import parse_component_file

DEFAULT_COMPONENT_ROOT = Path("research/components")


@dataclass(frozen=True)
class FrozenComponentRegistry:
    definitions: Mapping[ComponentFamily, Mapping[str, ComponentDefinition]]
    fingerprint: str

    def ids(self, family: ComponentFamily) -> tuple[str, ...]:
        return tuple(self.definitions.get(family, {}))

    def get(self, selection: ComponentSelection) -> ComponentDefinition:
        try:
            return self.definitions[selection.family][selection.id]
        except KeyError as error:
            raise ComponentRegistryError(
                f"unknown component id: {selection.family}/{selection.id}"
            ) from error

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "families": {
                family: {
                    component_id: {
                        "family": definition.family,
                        "id": definition.id,
                        "version": definition.manifest.version,
                        "source_hash": definition.identity.source_hash,
                    }
                    for component_id, definition in definitions.items()
                }
                for family, definitions in self.definitions.items()
            },
        }


def discover_component_registry(
    *,
    root: str | Path = DEFAULT_COMPONENT_ROOT,
    repo_root: str | Path | None = None,
) -> FrozenComponentRegistry:
    repo_root_path = Path.cwd() if repo_root is None else Path(repo_root)
    root_path = _resolve_root(Path(root), repo_root=repo_root_path)
    definitions: dict[ComponentFamily, dict[str, ComponentDefinition]] = {
        family: {} for family in COMPONENT_FAMILIES
    }
    if not root_path.exists():
        return _freeze(definitions)
    if root_path.is_symlink():
        raise ComponentRegistryError(f"{root_path}: component root must not be a symlink")
    _assert_inside_root(root_path, root_path)

    for family in COMPONENT_FAMILIES:
        family_root = root_path / family
        if not family_root.exists():
            continue
        for component_file in _component_files(family_root, root_path):
            definition = parse_component_file(
                component_file,
                family=family,
                repo_root=repo_root_path,
            )
            family_definitions = definitions[family]
            if definition.id in family_definitions:
                raise ComponentRegistryError(f"duplicate component id in {family}: {definition.id}")
            family_definitions[definition.id] = definition
    return _freeze(definitions)


def load_component_callable(definition: ComponentDefinition) -> Any:
    module_name = (
        "research.aegis_research.component_registry.loaded."
        f"{definition.family}.{definition.id}.{definition.identity.source_hash[:12]}"
    ).replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, definition.file_path)
    if spec is None or spec.loader is None:
        raise ComponentRegistryError(f"could not import component file: {definition.file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    try:
        component_callable = getattr(module, definition.callable_name)
    except AttributeError as error:
        raise ComponentRegistryError(
            f"component {definition.family}/{definition.id} missing callable {definition.callable_name!r}"
        ) from error
    if not callable(component_callable):
        raise ComponentRegistryError(
            f"component {definition.family}/{definition.id} callable {definition.callable_name!r} is not callable"
        )
    return component_callable


def _resolve_root(root: Path, *, repo_root: Path) -> Path:
    return (
        root.resolve(strict=False)
        if root.is_absolute()
        else (repo_root / root).resolve(strict=False)
    )


def _component_files(path: Path, root: Path) -> tuple[Path, ...]:
    if path.is_symlink():
        raise ComponentRegistryError(f"{path}: component directory must not be a symlink")
    _assert_inside_root(path, root)
    files = []
    for child in path.rglob("*"):
        if child.is_symlink():
            try:
                _assert_inside_root(child.resolve(strict=True), root)
            except FileNotFoundError as error:
                raise ComponentRegistryError(
                    f"{child}: component symlink target does not exist"
                ) from error
            raise ComponentRegistryError(f"{child}: component symlink is not allowed")
        if child.suffix == ".py" and child.is_file():
            _assert_inside_root(child, root)
            files.append(child)
    return tuple(sorted(files))


def _assert_inside_root(path: Path, root: Path) -> None:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as error:
        raise ComponentRegistryError(
            f"{path}: component file resolves outside approved root"
        ) from error


def _freeze(
    definitions: dict[ComponentFamily, dict[str, ComponentDefinition]],
) -> FrozenComponentRegistry:
    sorted_definitions: dict[ComponentFamily, Mapping[str, ComponentDefinition]] = {}
    for family in COMPONENT_FAMILIES:
        sorted_definitions[family] = MappingProxyType(dict(sorted(definitions[family].items())))
    frozen = MappingProxyType(sorted_definitions)
    return FrozenComponentRegistry(definitions=frozen, fingerprint=_registry_fingerprint(frozen))


def _registry_fingerprint(
    definitions: Mapping[ComponentFamily, Mapping[str, ComponentDefinition]],
) -> str:
    payload = {
        family: {
            component_id: {
                "manifest": definition.manifest.fingerprint_payload(),
                "callable": definition.callable_name,
                "source": definition.identity.public(),
            }
            for component_id, definition in family_definitions.items()
        }
        for family, family_definitions in definitions.items()
    }
    data = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()
