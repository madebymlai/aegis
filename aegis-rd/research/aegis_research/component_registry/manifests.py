from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter
from pydantic import (
    ValidationError as PydanticValidationError,
)

from research.aegis_research.component_registry.contracts import (
    COMPONENT_ENTRYPOINT,
    COMPONENT_LOOKBACK_ENTRYPOINT,
    COMPONENT_PARAM_SPACE_ENTRYPOINT,
    ComponentDefinition,
    ComponentFamily,
    ComponentRegistryError,
    ComponentSourceIdentity,
    IndicatorManifest,
    StrategyManifest,
)

COMPONENT_MANIFEST_NAME = "COMPONENT_MANIFEST"
COMPONENT_PERCENT_CELL_MARKER = "# %%"
COMPONENT_PERCENT_CELL_RE = re.compile(r"^# %%.*$", re.MULTILINE)
COMPONENT_MAIN_CELL_RE = re.compile(r"^# %%\s+main\b", re.MULTILINE)


def parse_component_file(
    path: Path,
    *,
    family: ComponentFamily,
    repo_root: Path,
) -> ComponentDefinition:
    source_bytes = path.read_bytes()
    manifest_payload, has_param_space, has_lookback = _read_static_declaration(
        path, source_bytes.decode()
    )
    manifest = build_manifest(manifest_payload, expected_family=family, path=path)
    return ComponentDefinition(
        _manifest=manifest,
        _file_path=path,
        identity=_source_identity(
            path,
            repo_root=repo_root,
            source_hash=hashlib.sha256(source_bytes).hexdigest(),
        ),
        _has_param_space=has_param_space,
        has_lookback=has_lookback,
    )


def build_manifest(
    payload: Any,
    *,
    expected_family: ComponentFamily,
    path: Path,
) -> IndicatorManifest | StrategyManifest:
    if not isinstance(payload, dict):
        raise ComponentRegistryError(f"{path}: {COMPONENT_MANIFEST_NAME} must be a literal mapping")
    adapter = _INDICATOR_ADAPTER if expected_family == "indicators" else _STRATEGY_ADAPTER
    try:
        return adapter.validate_python(dict(payload))
    except PydanticValidationError as e:
        raise ComponentRegistryError(_format_manifest_errors(e, path)) from e


def _read_static_declaration(path: Path, source: str) -> tuple[dict[str, Any], bool, bool]:
    percent_cell_markers = COMPONENT_PERCENT_CELL_RE.findall(source)
    if not percent_cell_markers:
        raise ComponentRegistryError(f"{path}: component files must use # %% percent cells")
    if any(marker.strip() == COMPONENT_PERCENT_CELL_MARKER for marker in percent_cell_markers):
        raise ComponentRegistryError(f"{path}: component percent cells must include a purpose")
    if COMPONENT_MAIN_CELL_RE.search(source) is None:
        raise ComponentRegistryError(f"{path}: component files must include a # %% main cell")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        raise ComponentRegistryError(f"{path}: invalid Python syntax") from error

    manifest: Any = None
    run_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    has_param_space = False
    has_lookback = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == COMPONENT_ENTRYPOINT:
                run_node = node
            elif node.name == COMPONENT_PARAM_SPACE_ENTRYPOINT:
                has_param_space = True
            elif node.name == COMPONENT_LOOKBACK_ENTRYPOINT:
                has_lookback = True
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if target.id == COMPONENT_MANIFEST_NAME:
                manifest = _literal_value(path, COMPONENT_MANIFEST_NAME, node.value)

    if manifest is None:
        raise ComponentRegistryError(f"{path}: missing {COMPONENT_MANIFEST_NAME}")
    if not isinstance(manifest, dict):
        raise ComponentRegistryError(f"{path}: {COMPONENT_MANIFEST_NAME} must be a literal mapping")
    if run_node is None:
        raise ComponentRegistryError(
            f"{path}: missing required component entry point {COMPONENT_ENTRYPOINT!r}"
        )
    if not ast.get_docstring(run_node):
        raise ComponentRegistryError(
            f"{path}: component entry point {COMPONENT_ENTRYPOINT!r} must have a docstring"
        )
    return manifest, has_param_space, has_lookback


def _literal_value(path: Path, name: str, node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (SyntaxError, ValueError) as error:
        raise ComponentRegistryError(f"{path}: {name} must be a Python literal") from error


def _format_manifest_errors(
    error: PydanticValidationError,
    path: Path,
) -> str:
    """Accumulate all pydantic errors for one manifest file into a single message."""
    messages: list[str] = []
    for entry in error.errors(include_url=False):
        loc = entry.get("loc", ())
        if loc:
            field = ".".join(str(p) for p in loc)
            messages.append(f"{path}: {field}: {entry['msg']}")
        else:
            messages.append(f"{path}: {entry['msg']}")
    return "; ".join(messages)


_INDICATOR_ADAPTER = TypeAdapter(IndicatorManifest)
_STRATEGY_ADAPTER = TypeAdapter(StrategyManifest)


def _source_identity(path: Path, *, repo_root: Path, source_hash: str) -> ComponentSourceIdentity:
    resolved_repo = repo_root.resolve(strict=False)
    resolved_path = path.resolve(strict=True)
    try:
        repo_relative = resolved_path.relative_to(resolved_repo).as_posix()
    except ValueError as error:
        raise ComponentRegistryError(
            f"{path}: component file resolves outside approved root"
        ) from error
    return ComponentSourceIdentity(
        repo_relative_path=repo_relative,
        source_hash=source_hash,
    )
