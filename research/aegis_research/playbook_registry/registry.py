from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import nbformat
from nbclient import NotebookClient

from research.aegis_research.component_registry import ComponentSelection, FrozenComponentRegistry
from research.aegis_research.component_registry.contracts import ComponentRegistryError
from research.aegis_research.component_registry.manifests import COMPONENT_ID_RE
from research.aegis_research.playbook_registry.contracts import (
    PLAYBOOK_FAMILIES,
    PLAYBOOK_STAGES,
    NotebookPlaybookDefinition,
    NotebookPlaybookManifest,
    PlaybookFamily,
    PlaybookRegistryError,
    PlaybookSelection,
    PlaybookSourceIdentity,
)

DEFAULT_PLAYBOOK_ROOT = Path("research/playbooks")
PLAYBOOK_METADATA_KEY = "aegis_playbook"


@dataclass(frozen=True)
class FrozenPlaybookRegistry:
    definitions: Mapping[PlaybookFamily, Mapping[str, NotebookPlaybookDefinition]]
    fingerprint: str

    def ids(self, family: PlaybookFamily) -> tuple[str, ...]:
        return tuple(self.definitions.get(family, {}))

    def get(self, selection: PlaybookSelection) -> NotebookPlaybookDefinition:
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
    definitions: dict[PlaybookFamily, dict[str, NotebookPlaybookDefinition]] = {
        family: {} for family in PLAYBOOK_FAMILIES
    }
    if not root_path.exists():
        return _freeze(definitions)
    if root_path.is_symlink():
        raise PlaybookRegistryError(f"{root_path}: playbook root must not be a symlink")
    _assert_inside_root(root_path, root_path)

    for family in PLAYBOOK_FAMILIES:
        family_root = root_path / family
        if not family_root.exists():
            continue
        _assert_playbook_directory(family_root, root_path)
        for notebook_path in sorted(family_root.rglob("*.ipynb")):
            _assert_playbook_file(notebook_path, root_path)
            definition = _parse_notebook_playbook(
                notebook_path,
                family=family,
                repo_root=repo_root_path,
                component_registry=component_registry,
            )
            family_definitions = definitions[family]
            if definition.id in family_definitions:
                raise PlaybookRegistryError(f"duplicate playbook id in {family}: {definition.id}")
            family_definitions[definition.id] = definition
    return _freeze(definitions)


def execute_notebook_playbook(
    definition: NotebookPlaybookDefinition,
    *,
    params: Mapping[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    notebook = nbformat.read(definition.file_path, as_version=4)
    params_json = json.dumps(dict(params or {}), sort_keys=True)
    setup = nbformat.v4.new_code_cell(
        "import json\n" f"AEGIS_PLAYBOOK_PARAMS = json.loads({params_json!r})"
    )
    capture = nbformat.v4.new_code_cell(
        "import json\n"
        "print('AEGIS_PLAYBOOK_RESULT_JSON=' + json.dumps(AEGIS_PLAYBOOK_RESULT, sort_keys=True))"
    )
    notebook.cells = [setup, *notebook.cells, capture]
    client = NotebookClient(notebook, timeout=timeout, kernel_name="python3")
    executed = client.execute()
    outputs = executed.cells[-1].get("outputs", [])
    for output in outputs:
        text = output.get("text")
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            if line.startswith("AEGIS_PLAYBOOK_RESULT_JSON="):
                result = json.loads(line.removeprefix("AEGIS_PLAYBOOK_RESULT_JSON="))
                if not isinstance(result, dict):
                    raise PlaybookRegistryError("playbook result must be a mapping")
                return result
    raise PlaybookRegistryError("playbook did not emit AEGIS_PLAYBOOK_RESULT")


def _parse_notebook_playbook(
    path: Path,
    *,
    family: PlaybookFamily,
    repo_root: Path,
    component_registry: FrozenComponentRegistry | None,
) -> NotebookPlaybookDefinition:
    try:
        notebook = nbformat.read(path, as_version=4)
    except Exception as error:
        raise PlaybookRegistryError(f"{path}: invalid notebook") from error
    metadata = notebook.metadata.get(PLAYBOOK_METADATA_KEY)
    if not isinstance(metadata, dict):
        raise PlaybookRegistryError(f"{path}: missing {PLAYBOOK_METADATA_KEY} metadata")
    manifest = _build_manifest(metadata, expected_family=family, path=path)
    if manifest.baseline_component_indicator_id is not None and component_registry is not None:
        try:
            component_registry.get(
                ComponentSelection("indicators", manifest.baseline_component_indicator_id)
            )
        except ComponentRegistryError as error:
            raise PlaybookRegistryError(
                f"{path}: unknown baseline component indicator {manifest.baseline_component_indicator_id!r}"
            ) from error
    return NotebookPlaybookDefinition(
        manifest=manifest,
        file_path=path,
        identity=_source_identity(path, repo_root=repo_root),
    )


def _build_manifest(
    metadata: dict[str, Any],
    *,
    expected_family: PlaybookFamily,
    path: Path,
) -> NotebookPlaybookManifest:
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
    return NotebookPlaybookManifest(
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
            raise PlaybookRegistryError(f"{path}: indicator playbooks must describe one indicator family")
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
    return root.resolve(strict=False) if root.is_absolute() else (repo_root / root).resolve(strict=False)


def _assert_playbook_directory(path: Path, root: Path) -> None:
    if path.is_symlink():
        raise PlaybookRegistryError(f"{path}: playbook directory must not be a symlink")
    _assert_inside_root(path, root)
    for child in path.rglob("*"):
        if child.is_symlink():
            _assert_inside_root(child.resolve(strict=True), root)
            raise PlaybookRegistryError(f"{child}: playbook symlink resolves outside approved root")


def _assert_playbook_file(path: Path, root: Path) -> None:
    if path.is_symlink():
        _assert_inside_root(path.resolve(strict=True), root)
        raise PlaybookRegistryError(f"{path}: playbook symlink resolves outside approved root")
    _assert_inside_root(path, root)


def _assert_inside_root(path: Path, root: Path) -> None:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as error:
        raise PlaybookRegistryError(f"{path}: playbook file resolves outside approved root") from error


def _source_identity(path: Path, *, repo_root: Path) -> PlaybookSourceIdentity:
    resolved_repo = repo_root.resolve(strict=False)
    resolved_path = path.resolve(strict=True)
    try:
        repo_relative = resolved_path.relative_to(resolved_repo).as_posix()
    except ValueError as error:
        raise PlaybookRegistryError(f"{path}: playbook file resolves outside approved root") from error
    return PlaybookSourceIdentity(
        repo_relative_path=repo_relative,
        source_hash=hashlib.sha256(resolved_path.read_bytes()).hexdigest(),
    )


def _freeze(
    definitions: dict[PlaybookFamily, dict[str, NotebookPlaybookDefinition]],
) -> FrozenPlaybookRegistry:
    sorted_definitions: dict[PlaybookFamily, Mapping[str, NotebookPlaybookDefinition]] = {}
    for family in PLAYBOOK_FAMILIES:
        sorted_definitions[family] = MappingProxyType(dict(sorted(definitions[family].items())))
    frozen = MappingProxyType(sorted_definitions)
    return FrozenPlaybookRegistry(definitions=frozen, fingerprint=_registry_fingerprint(frozen))


def _registry_fingerprint(
    definitions: Mapping[PlaybookFamily, Mapping[str, NotebookPlaybookDefinition]],
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
