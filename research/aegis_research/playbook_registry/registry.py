from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from research.aegis_research.component_registry import ComponentSelection, FrozenComponentRegistry
from research.aegis_research.component_registry.contracts import ComponentRegistryError
from research.aegis_research.component_registry.manifests import COMPONENT_ID_RE
from research.aegis_research.playbook_registry.contracts import (
    PLAYBOOK_FAMILIES,
    PLAYBOOK_STAGES,
    PlaybookDefinition,
    PlaybookFamily,
    PlaybookManifest,
    PlaybookRegistryError,
    PlaybookSelection,
    PlaybookSourceIdentity,
)

DEFAULT_PLAYBOOK_ROOT = Path("research/playbooks")
PLAYBOOK_MANIFEST_NAME = "PLAYBOOK_MANIFEST"
PLAYBOOK_CALLABLE_NAME = "PLAYBOOK_CALLABLE"
PLAYBOOK_SWEEP_RESULT_SCHEMA = "playbook_sweep_result.v1"


@dataclass(frozen=True)
class FrozenPlaybookRegistry:
    definitions: Mapping[PlaybookFamily, Mapping[str, PlaybookDefinition]]
    fingerprint: str

    def ids(self, family: PlaybookFamily) -> tuple[str, ...]:
        return tuple(self.definitions.get(family, {}))

    def get(self, selection: PlaybookSelection) -> PlaybookDefinition:
        try:
            return self.definitions[selection.family][selection.id]
        except KeyError as error:
            raise PlaybookRegistryError(
                f"unknown playbook id: {selection.family}/{selection.id}"
            ) from error


def discover_playbook_registry(
    *,
    root: str | Path = DEFAULT_PLAYBOOK_ROOT,
    repo_root: str | Path | None = None,
    component_registry: FrozenComponentRegistry | None = None,
) -> FrozenPlaybookRegistry:
    repo_root_path = Path.cwd() if repo_root is None else Path(repo_root)
    root_path = _resolve_root(Path(root), repo_root=repo_root_path)
    definitions: dict[PlaybookFamily, dict[str, PlaybookDefinition]] = {
        family: {} for family in PLAYBOOK_FAMILIES
    }
    if not root_path.exists():
        return _freeze(definitions)
    if root_path.is_symlink():
        raise PlaybookRegistryError(f"{root_path}: playbook root must not be a symlink")
    _assert_inside_root(root_path, root_path)
    _reject_unsupported_family_files(root_path)

    for family in PLAYBOOK_FAMILIES:
        family_root = root_path / family
        if not family_root.exists():
            continue
        for playbook_path in _playbook_files(family_root, root_path):
            definition = _parse_playbook(
                playbook_path,
                family=family,
                repo_root=repo_root_path,
                component_registry=component_registry,
            )
            family_definitions = definitions[family]
            if definition.id in family_definitions:
                raise PlaybookRegistryError(f"duplicate playbook id in {family}: {definition.id}")
            family_definitions[definition.id] = definition
    return _freeze(definitions)


def load_playbook_callable(definition: PlaybookDefinition) -> Any:
    module_name = (
        "research.aegis_research.playbook_registry.loaded."
        f"{definition.family}.{definition.id}.{definition.identity.source_hash[:12]}"
    ).replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, definition.file_path)
    if spec is None or spec.loader is None:
        raise PlaybookRegistryError(f"could not import playbook file: {definition.file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    try:
        playbook_callable = getattr(module, definition.callable_name)
    except AttributeError as error:
        raise PlaybookRegistryError(
            f"playbook {definition.family}/{definition.id} missing callable {definition.callable_name!r}"
        ) from error
    if not callable(playbook_callable):
        raise PlaybookRegistryError(
            f"playbook {definition.family}/{definition.id} callable {definition.callable_name!r} is not callable"
        )
    return playbook_callable


def _parse_playbook(
    path: Path,
    *,
    family: PlaybookFamily,
    repo_root: Path,
    component_registry: FrozenComponentRegistry | None,
) -> PlaybookDefinition:
    return _parse_python_playbook(
        path,
        family=family,
        repo_root=repo_root,
        component_registry=component_registry,
    )


def _parse_python_playbook(
    path: Path,
    *,
    family: PlaybookFamily,
    repo_root: Path,
    component_registry: FrozenComponentRegistry | None,
) -> PlaybookDefinition:
    source_bytes = path.read_bytes()
    source = source_bytes.decode()
    manifest_payload, callable_name = _read_python_playbook_declaration(path, source)
    if "# %%" not in source:
        raise PlaybookRegistryError(f"{path}: playbooks must use # %% percent cells")
    manifest = _build_manifest(manifest_payload, expected_family=family, path=path)
    if manifest.baseline_component_indicator_id is not None and component_registry is not None:
        try:
            component_registry.get(
                ComponentSelection("indicators", manifest.baseline_component_indicator_id)
            )
        except ComponentRegistryError as error:
            raise PlaybookRegistryError(
                f"{path}: unknown baseline component indicator {manifest.baseline_component_indicator_id!r}"
            ) from error
    return PlaybookDefinition(
        manifest=manifest,
        file_path=path,
        identity=_source_identity(
            path,
            repo_root=repo_root,
            source_hash=hashlib.sha256(source_bytes).hexdigest(),
        ),
        callable_name=callable_name,
    )


def _read_python_playbook_declaration(path: Path, source: str) -> tuple[dict[str, Any], str]:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        raise PlaybookRegistryError(f"{path}: invalid Python syntax") from error

    manifest: Any = None
    callable_name: Any = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id == PLAYBOOK_MANIFEST_NAME:
            manifest = _literal_value(path, PLAYBOOK_MANIFEST_NAME, node.value)
        elif target.id == PLAYBOOK_CALLABLE_NAME:
            callable_name = _literal_value(path, PLAYBOOK_CALLABLE_NAME, node.value)

    if manifest is None:
        raise PlaybookRegistryError(f"{path}: missing {PLAYBOOK_MANIFEST_NAME}")
    if callable_name is None:
        raise PlaybookRegistryError(f"{path}: missing {PLAYBOOK_CALLABLE_NAME}")
    if not isinstance(manifest, dict):
        raise PlaybookRegistryError(f"{path}: {PLAYBOOK_MANIFEST_NAME} must be a literal mapping")
    if not isinstance(callable_name, str) or not callable_name:
        raise PlaybookRegistryError(f"{path}: {PLAYBOOK_CALLABLE_NAME} must be a literal string")
    _assert_dynamic_sweep_candidate_ids(path, tree, manifest)
    return manifest, callable_name


def _literal_value(path: Path, name: str, node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (SyntaxError, ValueError) as error:
        raise PlaybookRegistryError(f"{path}: {name} must be a Python literal") from error


def _assert_dynamic_sweep_candidate_ids(
    path: Path,
    tree: ast.AST,
    manifest: Mapping[str, Any],
) -> None:
    if manifest.get("result_schema") != PLAYBOOK_SWEEP_RESULT_SCHEMA:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            if _literal_dict_key(key) != "candidate_id":
                continue
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            params_node = _dict_value(node, "params")
            if params_node is None or _is_empty_literal_dict(params_node):
                continue
            raise PlaybookRegistryError(
                f"{path}: sweep candidate_id values with params must be derived from params; "
                "use candidate_id_from_params instead of string literals"
            )


def _literal_dict_key(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _dict_value(node: ast.Dict, key_name: str) -> ast.AST | None:
    for key, value in zip(node.keys, node.values, strict=True):
        if _literal_dict_key(key) == key_name:
            return value
    return None


def _is_empty_literal_dict(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Dict) and not node.keys


def _build_manifest(
    metadata: dict[str, Any],
    *,
    expected_family: PlaybookFamily,
    path: Path,
) -> PlaybookManifest:
    family = metadata.get("family")
    if family not in PLAYBOOK_FAMILIES:
        raise PlaybookRegistryError(f"{path}: playbook family must be one of {PLAYBOOK_FAMILIES}")
    if family != expected_family:
        raise PlaybookRegistryError(
            f"{path}: playbook family {family!r} does not match {expected_family!r} directory"
        )
    playbook_id = metadata.get("id")
    if not isinstance(playbook_id, str) or not playbook_id:
        raise PlaybookRegistryError(f"{path}: playbook id must be a non-empty string")
    if not COMPONENT_ID_RE.fullmatch(playbook_id) or playbook_id in {".", ".."}:
        raise PlaybookRegistryError(
            f"{path}: playbook id must contain only letters, numbers, dots, underscores, and hyphens"
        )
    version = metadata.get("version")
    if not isinstance(version, str) or not version:
        raise PlaybookRegistryError(f"{path}: playbook version must be a non-empty string")
    stages = _string_tuple(metadata, "stages", path, non_empty=True)
    unsupported = sorted(set(stages) - PLAYBOOK_STAGES)
    if unsupported:
        raise PlaybookRegistryError(f"{path}: unsupported stage {unsupported[0]!r}")
    accepted_inputs = _string_tuple(metadata, "accepted_inputs", path)
    result_schema = metadata.get("result_schema")
    if not isinstance(result_schema, str) or not result_schema:
        raise PlaybookRegistryError(f"{path}: result_schema must be a non-empty string")
    indicator_family = _indicator_family(metadata, family, path)
    baseline = metadata.get("baseline_component_indicator_id")
    if baseline is not None and (not isinstance(baseline, str) or not baseline):
        raise PlaybookRegistryError(
            f"{path}: baseline_component_indicator_id must be a non-empty string"
        )
    return PlaybookManifest(
        family=family,
        id=playbook_id,
        version=version,
        stages=stages,
        accepted_inputs=accepted_inputs,
        result_schema=result_schema,
        indicator_family=indicator_family,
        baseline_component_indicator_id=baseline,
        payload=dict(metadata),
    )


def _indicator_family(metadata: dict[str, Any], family: str, path: Path) -> str | None:
    if family != "indicators":
        return None
    if "indicator_families" in metadata:
        families = metadata["indicator_families"]
        if not isinstance(families, list) or len(families) != 1:
            raise PlaybookRegistryError(
                f"{path}: indicator playbooks must describe one indicator family"
            )
        value = families[0]
        if not isinstance(value, str) or not value:
            raise PlaybookRegistryError(f"{path}: indicator family must be a non-empty string")
        return value
    value = metadata.get("indicator_family")
    if not isinstance(value, str) or not value:
        raise PlaybookRegistryError(f"{path}: indicator_family must be a non-empty string")
    return value


def _string_tuple(
    metadata: dict[str, Any],
    key: str,
    path: Path,
    *,
    non_empty: bool = False,
) -> tuple[str, ...]:
    value = metadata.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise PlaybookRegistryError(f"{path}: {key} must be a list of non-empty strings")
    if non_empty and not value:
        raise PlaybookRegistryError(f"{path}: {key} must not be empty")
    return tuple(value)


def _resolve_root(root: Path, *, repo_root: Path) -> Path:
    return (
        root.resolve(strict=False)
        if root.is_absolute()
        else (repo_root / root).resolve(strict=False)
    )


def _playbook_files(path: Path, root: Path) -> tuple[Path, ...]:
    if path.is_symlink():
        raise PlaybookRegistryError(f"{path}: playbook directory must not be a symlink")
    _assert_inside_root(path, root)
    files = []
    for child in path.rglob("*"):
        if child.is_symlink():
            try:
                _assert_inside_root(child.resolve(strict=True), root)
            except FileNotFoundError as error:
                raise PlaybookRegistryError(
                    f"{child}: playbook symlink target does not exist"
                ) from error
            raise PlaybookRegistryError(f"{child}: playbook symlink is not allowed")
        if child.suffix == ".py" and child.is_file():
            _assert_inside_root(child, root)
            files.append(child)
    return tuple(sorted(files))


def _reject_unsupported_family_files(root: Path) -> None:
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in PLAYBOOK_FAMILIES:
            continue
        files = _playbook_files(child, root)
        if files:
            raise PlaybookRegistryError(
                f"{child}: unsupported playbook family; labels must be reviewed components"
            )


def _assert_inside_root(path: Path, root: Path) -> None:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as error:
        raise PlaybookRegistryError(
            f"{path}: playbook file resolves outside approved root"
        ) from error


def _source_identity(path: Path, *, repo_root: Path, source_hash: str) -> PlaybookSourceIdentity:
    resolved_repo = repo_root.resolve(strict=False)
    resolved_path = path.resolve(strict=True)
    try:
        repo_relative = resolved_path.relative_to(resolved_repo).as_posix()
    except ValueError as error:
        raise PlaybookRegistryError(
            f"{path}: playbook file resolves outside approved root"
        ) from error
    return PlaybookSourceIdentity(
        repo_relative_path=repo_relative,
        source_hash=source_hash,
    )


def _freeze(
    definitions: dict[PlaybookFamily, dict[str, PlaybookDefinition]],
) -> FrozenPlaybookRegistry:
    sorted_definitions: dict[PlaybookFamily, Mapping[str, PlaybookDefinition]] = {}
    for family in PLAYBOOK_FAMILIES:
        sorted_definitions[family] = MappingProxyType(dict(sorted(definitions[family].items())))
    frozen = MappingProxyType(sorted_definitions)
    return FrozenPlaybookRegistry(definitions=frozen, fingerprint=_registry_fingerprint(frozen))


def _registry_fingerprint(
    definitions: Mapping[PlaybookFamily, Mapping[str, PlaybookDefinition]],
) -> str:
    payload = {
        family: {
            playbook_id: {
                "manifest": definition.manifest.fingerprint_payload(),
                "source": definition.identity.public(),
            }
            for playbook_id, definition in family_definitions.items()
        }
        for family, family_definitions in definitions.items()
    }
    data = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()
