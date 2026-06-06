from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any

from research.aegis_research.component_registry.contracts import (
    COMPONENT_FAMILIES,
    ComponentDefinition,
    ComponentFamily,
    ComponentRegistryError,
    ComponentSourceIdentity,
    IndicatorManifest,
    StrategyManifest,
)
from research.aegis_research.configuration.schema import has_data_array_token_shape

COMPONENT_MANIFEST_NAME = "COMPONENT_MANIFEST"
COMPONENT_CALLABLE_NAME = "COMPONENT_CALLABLE"
COMPONENT_PERCENT_CELL_MARKER = "# %%"
COMPONENT_PERCENT_CELL_RE = re.compile(r"^# %%.*$", re.MULTILINE)
COMPONENT_MAIN_CELL_RE = re.compile(r"^# %%\s+main\b", re.MULTILINE)
COMPONENT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
STRATEGY_ALLOCATION_OUTPUTS = {"active", "scores", "ranks", "target_weights"}
STRATEGY_FORBIDDEN_KEYS = {
    "costs",
    "direction",
    "execution_timing",
    "fees",
    "gross_cap",
    "net_cap",
    "portfolio",
    "portfolio_config",
    "size",
    "sizing",
    "slippage",
}


def parse_component_file(
    path: Path,
    *,
    family: ComponentFamily,
    repo_root: Path,
) -> ComponentDefinition:
    source_bytes = path.read_bytes()
    manifest_payload, callable_name = _read_static_declaration(path, source_bytes.decode())
    manifest = build_manifest(manifest_payload, expected_family=family, path=path)
    return ComponentDefinition(
        manifest=manifest,
        callable_name=callable_name,
        file_path=path,
        identity=_source_identity(
            path,
            repo_root=repo_root,
            source_hash=hashlib.sha256(source_bytes).hexdigest(),
        ),
    )


def build_manifest(
    payload: Any,
    *,
    expected_family: ComponentFamily,
    path: Path,
) -> IndicatorManifest | StrategyManifest:
    if not isinstance(payload, dict):
        raise ComponentRegistryError(f"{path}: {COMPONENT_MANIFEST_NAME} must be a literal mapping")
    payload = dict(payload)
    _validate_common(payload, expected_family=expected_family, path=path)
    family = payload["family"]
    if family == "indicators":
        return _indicator_manifest(payload, path)
    if family == "strategies":
        return _strategy_manifest(payload, path)
    raise ComponentRegistryError(f"{path}: component family must be one of {COMPONENT_FAMILIES}")


def _read_static_declaration(path: Path, source: str) -> tuple[dict[str, Any], str]:
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
    callable_name: Any = None
    callable_node: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == callable_name:
            callable_node = node
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if target.id == COMPONENT_MANIFEST_NAME:
                manifest = _literal_value(path, COMPONENT_MANIFEST_NAME, node.value)
            elif target.id == COMPONENT_CALLABLE_NAME:
                callable_name = _literal_value(path, COMPONENT_CALLABLE_NAME, node.value)

    if manifest is None:
        raise ComponentRegistryError(f"{path}: missing {COMPONENT_MANIFEST_NAME}")
    if callable_name is None:
        raise ComponentRegistryError(f"{path}: missing {COMPONENT_CALLABLE_NAME}")
    if not isinstance(callable_name, str) or not callable_name:
        raise ComponentRegistryError(f"{path}: {COMPONENT_CALLABLE_NAME} must be a literal string")
    if not isinstance(manifest, dict):
        raise ComponentRegistryError(f"{path}: {COMPONENT_MANIFEST_NAME} must be a literal mapping")
    if callable_node is None:
        for node in tree.body:
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name == callable_name
            ):
                callable_node = node
                break
    if callable_node is None:
        raise ComponentRegistryError(f"{path}: missing callable function {callable_name!r}")
    if not ast.get_docstring(callable_node):
        raise ComponentRegistryError(
            f"{path}: component callable {callable_name!r} must have a docstring"
        )
    return manifest, callable_name


def _literal_value(path: Path, name: str, node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (SyntaxError, ValueError) as error:
        raise ComponentRegistryError(f"{path}: {name} must be a Python literal") from error


def _validate_common(payload: dict[str, Any], *, expected_family: str, path: Path) -> None:
    family = payload.get("family")
    if family not in COMPONENT_FAMILIES:
        raise ComponentRegistryError(
            f"{path}: component family must be one of {COMPONENT_FAMILIES}"
        )
    if family != expected_family:
        raise ComponentRegistryError(
            f"{path}: component family {family!r} does not match {expected_family!r} directory"
        )
    component_id = payload.get("id")
    if not isinstance(component_id, str) or not component_id:
        raise ComponentRegistryError(f"{path}: component id must be a non-empty string")
    if not COMPONENT_ID_RE.fullmatch(component_id) or component_id in {".", ".."}:
        raise ComponentRegistryError(
            f"{path}: component id must contain only letters, numbers, dots, underscores, and hyphens"
        )
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise ComponentRegistryError(f"{path}: component version must be a non-empty string")


def _indicator_manifest(payload: dict[str, Any], path: Path) -> IndicatorManifest:
    input_names = _required_input_names(payload, path)
    param_names = _required_string_tuple(payload, "param_names", path, allow_empty=True)
    output_names = _required_string_tuple(payload, "output_names", path)
    defaults = _optional_mapping(payload, "defaults", path)
    _validate_param_defaults(defaults, param_names, path)
    wide_callable = _required_string(payload, "wide_callable", path)
    param_space_callable = _optional_string(payload, "param_space_callable", path)
    bar_aligned = payload.get("bar_aligned", True)
    if bar_aligned is not True:
        raise ComponentRegistryError(f"{path}: indicator components must be bar-aligned in v1")
    return IndicatorManifest(
        family="indicators",
        id=payload["id"],
        version=payload["version"],
        payload=payload,
        input_names=input_names,
        param_names=param_names,
        output_names=output_names,
        defaults=defaults,
        wide_callable=wide_callable,
        param_space_callable=param_space_callable,
        bar_aligned=True,
    )


def _strategy_manifest(payload: dict[str, Any], path: Path) -> StrategyManifest:
    input_names = _required_input_names(payload, path)
    param_names = _optional_string_tuple(payload, "param_names", path)
    output_name = _required_string(payload, "output_name", path)
    consumes_outputs = _optional_string_tuple(payload, "consumes_outputs", path)
    defaults = _optional_mapping(payload, "defaults", path)
    _validate_param_defaults(defaults, param_names, path)
    wide_callable = _required_string(payload, "wide_callable", path)
    param_space_callable = _optional_string(payload, "param_space_callable", path)
    if output_name not in STRATEGY_ALLOCATION_OUTPUTS:
        raise ComponentRegistryError(
            f"{path}: unsupported allocation output {output_name!r}; "
            f"registered shapes are {STRATEGY_ALLOCATION_OUTPUTS}"
        )
    owns_portfolio = payload.get("owns_portfolio", False)
    if owns_portfolio is not False:
        raise ComponentRegistryError(f"{path}: strategy components must not own portfolio behavior")
    for key in STRATEGY_FORBIDDEN_KEYS:
        if key in payload:
            raise ComponentRegistryError(f"{path}: strategy manifest field {key!r} is forbidden")
    return StrategyManifest(
        family="strategies",
        id=payload["id"],
        version=payload["version"],
        payload=payload,
        input_names=input_names,
        param_names=param_names,
        output_name=output_name,
        consumes_outputs=consumes_outputs,
        defaults=defaults,
        wide_callable=wide_callable,
        param_space_callable=param_space_callable,
        owns_portfolio=False,
    )


def _required_input_names(payload: dict[str, Any], path: Path) -> tuple[str, ...]:
    input_names = _required_string_tuple(payload, "input_names", path)
    invalid = [name for name in input_names if not has_data_array_token_shape(name)]
    if invalid:
        raise ComponentRegistryError(
            f"{path}: input_names must contain VBT feature names without surrounding "
            f"whitespace or control characters: {invalid}"
        )
    return input_names


def _required_string(payload: dict[str, Any], key: str, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ComponentRegistryError(f"{path}: {key} must be a non-empty string")
    return value


def _required_string_tuple(
    payload: dict[str, Any],
    key: str,
    path: Path,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ComponentRegistryError(f"{path}: {key} must be a literal list of strings")
    if not allow_empty and not value:
        raise ComponentRegistryError(f"{path}: {key} must not be empty")
    if not all(isinstance(item, str) and item for item in value):
        raise ComponentRegistryError(f"{path}: {key} must contain only non-empty strings")
    return tuple(value)


def _optional_string_tuple(payload: dict[str, Any], key: str, path: Path) -> tuple[str, ...]:
    if key not in payload:
        return ()
    return _required_string_tuple(payload, key, path, allow_empty=True)


def _optional_string(payload: dict[str, Any], key: str, path: Path) -> str | None:
    if key not in payload:
        return None
    return _required_string(payload, key, path)


def _optional_mapping(payload: dict[str, Any], key: str, path: Path) -> dict[str, Any]:
    if key not in payload:
        return {}
    value = payload[key]
    if not isinstance(value, dict):
        raise ComponentRegistryError(f"{path}: {key} must be a literal mapping")
    if not all(isinstance(item, str) and item for item in value):
        raise ComponentRegistryError(f"{path}: {key} keys must be non-empty strings")
    return dict(value)


def _validate_param_defaults(
    defaults: dict[str, Any],
    param_names: tuple[str, ...],
    path: Path,
) -> None:
    unknown = sorted(set(defaults) - set(param_names))
    if unknown:
        raise ComponentRegistryError(
            f"{path}: defaults keys must be declared in param_names; unknown: {unknown}"
        )


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
