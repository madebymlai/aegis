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
    LabelManifest,
    StrategyManifest,
)
from research.aegis_research.configuration.schema import LABEL_TARGET_ROLES

COMPONENT_MANIFEST_NAME = "COMPONENT_MANIFEST"
COMPONENT_CALLABLE_NAME = "COMPONENT_CALLABLE"
COMPONENT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
LABEL_TARGET_KINDS = {"binary_classification", "continuous", "regime", "sparse_event"}
STRATEGY_SIGNAL_OUTPUTS = {"entries", "exits"}
STRATEGY_FORBIDDEN_KEYS = {
    "costs",
    "direction",
    "entry_budget",
    "execution_timing",
    "fees",
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
    manifest_payload, callable_name = _read_static_declaration(path)
    manifest = build_manifest(manifest_payload, expected_family=family, path=path)
    return ComponentDefinition(
        manifest=manifest,
        callable_name=callable_name,
        file_path=path,
        identity=_source_identity(path, repo_root=repo_root),
    )


def build_manifest(
    payload: Any,
    *,
    expected_family: ComponentFamily,
    path: Path,
) -> LabelManifest | IndicatorManifest | StrategyManifest:
    if not isinstance(payload, dict):
        raise ComponentRegistryError(f"{path}: {COMPONENT_MANIFEST_NAME} must be a literal mapping")
    payload = dict(payload)
    _validate_common(payload, expected_family=expected_family, path=path)
    family = payload["family"]
    if family == "labels":
        return _label_manifest(payload, path)
    if family == "indicators":
        return _indicator_manifest(payload, path)
    if family == "strategies":
        return _strategy_manifest(payload, path)
    raise ComponentRegistryError(f"{path}: component family must be one of {COMPONENT_FAMILIES}")


def _read_static_declaration(path: Path) -> tuple[dict[str, Any], str]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as error:
        raise ComponentRegistryError(f"{path}: invalid Python syntax") from error

    manifest: Any = None
    callable_name: Any = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
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
    return manifest, callable_name


def _literal_value(path: Path, name: str, node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (SyntaxError, ValueError) as error:
        raise ComponentRegistryError(f"{path}: {name} must be a Python literal") from error


def _validate_common(payload: dict[str, Any], *, expected_family: str, path: Path) -> None:
    family = payload.get("family")
    if family not in COMPONENT_FAMILIES:
        raise ComponentRegistryError(f"{path}: component family must be one of {COMPONENT_FAMILIES}")
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


def _label_manifest(payload: dict[str, Any], path: Path) -> LabelManifest:
    target_role = _required_string(payload, "target_role", path)
    target_kind = _required_string(payload, "target_kind", path)
    if target_role not in LABEL_TARGET_ROLES:
        raise ComponentRegistryError(f"{path}: unsupported label target_role {target_role!r}")
    if target_kind not in LABEL_TARGET_KINDS:
        raise ComponentRegistryError(f"{path}: unsupported label target_kind {target_kind!r}")
    output_names = _required_string_tuple(payload, "output_names", path)
    return LabelManifest(
        family="labels",
        id=payload["id"],
        version=payload["version"],
        payload=payload,
        target_role=target_role,
        target_kind=target_kind,
        output_names=output_names,
    )


def _indicator_manifest(payload: dict[str, Any], path: Path) -> IndicatorManifest:
    input_names = _required_string_tuple(payload, "input_names", path, allow_empty=True)
    param_names = _required_string_tuple(payload, "param_names", path, allow_empty=True)
    output_names = _required_string_tuple(payload, "output_names", path)
    default_outputs = _required_string_tuple(payload, "default_outputs", path)
    supported_transforms = _required_string_tuple(payload, "supported_transforms", path)
    if missing := sorted(set(default_outputs) - set(output_names)):
        raise ComponentRegistryError(f"{path}: default_outputs not declared in output_names: {missing}")
    default_model_features = _default_model_features(payload, output_names, supported_transforms, path)
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
        default_outputs=default_outputs,
        default_model_features=default_model_features,
        supported_transforms=supported_transforms,
        bar_aligned=True,
    )


def _strategy_manifest(payload: dict[str, Any], path: Path) -> StrategyManifest:
    signal_outputs = _required_string_tuple(payload, "signal_outputs", path)
    if unsupported := sorted(set(signal_outputs) - STRATEGY_SIGNAL_OUTPUTS):
        raise ComponentRegistryError(f"{path}: unsupported strategy outputs: {unsupported}")
    if set(signal_outputs) != STRATEGY_SIGNAL_OUTPUTS:
        raise ComponentRegistryError(f"{path}: strategy components must emit entries and exits")
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
        signal_outputs=signal_outputs,
        owns_portfolio=False,
    )


def _default_model_features(
    payload: dict[str, Any],
    output_names: tuple[str, ...],
    supported_transforms: tuple[str, ...],
    path: Path,
) -> tuple[dict[str, str], ...]:
    raw = payload.get("default_model_features")
    if not isinstance(raw, list) or not raw:
        raise ComponentRegistryError(f"{path}: default_model_features must be a non-empty literal list")
    rows: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ComponentRegistryError(f"{path}: default_model_features[{index}] must be a mapping")
        output = item.get("output")
        transform = item.get("transform", "identity")
        if not isinstance(output, str) or output not in output_names:
            raise ComponentRegistryError(
                f"{path}: default_model_features[{index}].output must be one of {output_names}"
            )
        if not isinstance(transform, str) or transform not in supported_transforms:
            raise ComponentRegistryError(
                f"{path}: default_model_features[{index}].transform must be one of {supported_transforms}"
            )
        rows.append({"output": output, "transform": transform})
    return tuple(rows)


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


def _source_identity(path: Path, *, repo_root: Path) -> ComponentSourceIdentity:
    resolved_repo = repo_root.resolve(strict=False)
    resolved_path = path.resolve(strict=True)
    try:
        repo_relative = resolved_path.relative_to(resolved_repo).as_posix()
    except ValueError as error:
        raise ComponentRegistryError(f"{path}: component file resolves outside approved root") from error
    return ComponentSourceIdentity(
        repo_relative_path=repo_relative,
        source_hash=hashlib.sha256(resolved_path.read_bytes()).hexdigest(),
    )
