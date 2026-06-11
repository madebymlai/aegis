from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)

from research.aegis_research.component_registry.contracts import (
    COMPONENT_ENTRYPOINT,
    COMPONENT_PARAM_SPACE_ENTRYPOINT,
    STRATEGY_ALLOCATION_OUTPUTS,
    ComponentDefinition,
    ComponentFamily,
    ComponentRegistryError,
    ComponentSourceIdentity,
    IndicatorManifest,
    StrategyManifest,
)
from research.aegis_research.configuration.field_types import (
    ComponentIdStr,
    NonEmptyStr,
)
from research.aegis_research.configuration.schema import has_data_array_token_shape

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
    manifest_payload, has_param_space = _read_static_declaration(path, source_bytes.decode())
    manifest = build_manifest(manifest_payload, expected_family=family, path=path)
    return ComponentDefinition(
        manifest=manifest,
        file_path=path,
        identity=_source_identity(
            path,
            repo_root=repo_root,
            source_hash=hashlib.sha256(source_bytes).hexdigest(),
        ),
        has_param_space=has_param_space,
    )

def build_manifest(
    payload: Any,
    *,
    expected_family: ComponentFamily,
    path: Path,
) -> IndicatorManifest | StrategyManifest:
    if not isinstance(payload, dict):
        raise ComponentRegistryError(
            f"{path}: {COMPONENT_MANIFEST_NAME} must be a literal mapping"
        )
    payload = dict(payload)
    try:
        if expected_family == "indicators":
            indicator = _INDICATOR_ADAPTER.validate_python(payload, strict=True)
            return _build_indicator_manifest(indicator)
        strategy = _STRATEGY_ADAPTER.validate_python(payload, strict=True)
        return _build_strategy_manifest(strategy)
    except PydanticValidationError as e:
        raise ComponentRegistryError(
            _format_manifest_errors(e, path)
        ) from e

def _read_static_declaration(path: Path, source: str) -> tuple[dict[str, Any], bool]:
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
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == COMPONENT_ENTRYPOINT:
                run_node = node
            elif node.name == COMPONENT_PARAM_SPACE_ENTRYPOINT:
                has_param_space = True
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
    return manifest, has_param_space

def _literal_value(path: Path, name: str, node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (SyntaxError, ValueError) as error:
        raise ComponentRegistryError(f"{path}: {name} must be a Python literal") from error

# ── Pydantic manifest payload models ──────────────────────────────────────

def _validate_manifest_input_name(token: str) -> str:
    """Pydantic item-validator: input_names must be VBT feature names."""
    if not has_data_array_token_shape(token):
        raise ValueError(
            "must be a VBT feature name without surrounding whitespace or control characters"
        )
    return token

def _validate_manifest_output_name(token: str) -> str:
    """Pydantic item-validator: output_names must be VBT feature names."""
    if not has_data_array_token_shape(token):
        raise ValueError(
            "must be a VBT feature name without surrounding whitespace or control characters"
        )
    return token

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

_ManifestInputName = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_validate_manifest_input_name),
]

_ManifestOutputName = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_validate_manifest_output_name),
]

class _BaseManifestPayload(BaseModel):
    """Common pydantic model for indicator and strategy manifest payloads."""

    model_config = ConfigDict(extra="forbid", strict=True)

    family: ComponentFamily
    id: ComponentIdStr
    version: NonEmptyStr
    input_names: list[_ManifestInputName]
    param_names: list[NonEmptyStr] = []
    defaults: dict[str, Any] = {}

    @model_validator(mode="after")
    def _reject_dot_ids(self) -> _BaseManifestPayload:
        if self.id in {".", ".."}:
            raise ValueError("component id must not be '.' or '..'")
        return self

    @model_validator(mode="after")
    def _check_defaults_in_params(self) -> _BaseManifestPayload:
        unknown = sorted(set(self.defaults) - set(self.param_names))
        if unknown:
            raise ValueError(
                f"defaults keys must be declared in param_names; unknown: {unknown}"
            )
        return self

class _IndicatorManifestPayload(_BaseManifestPayload):
    """Pydantic model for indicator manifest payload validation."""

    family: Literal["indicators"]
    output_names: list[_ManifestOutputName]
    bar_aligned: Literal[True] = True

    @model_validator(mode="after")
    def _check_output_names(self) -> _IndicatorManifestPayload:
        if not self.output_names:
            raise ValueError("output_names must not be empty")
        duplicates = sorted(
            {name for name in self.output_names if self.output_names.count(name) > 1}
        )
        if duplicates:
            raise ValueError(f"output_names must be unique; duplicates: {duplicates}")
        return self

class _StrategyManifestPayload(_BaseManifestPayload):
    """Pydantic model for strategy manifest payload validation."""

    family: Literal["strategies"]
    output_name: NonEmptyStr
    consumes_outputs: list[NonEmptyStr] = []
    owns_portfolio: Literal[False] = False

    @model_validator(mode="after")
    def _check_output_name_allowed(self) -> _StrategyManifestPayload:
        if self.output_name not in STRATEGY_ALLOCATION_OUTPUTS:
            raise ValueError(
                f"unsupported allocation output {self.output_name!r}; "
                f"registered shapes are {sorted(STRATEGY_ALLOCATION_OUTPUTS)}"
            )
        return self

_INDICATOR_ADAPTER = TypeAdapter(_IndicatorManifestPayload)
_STRATEGY_ADAPTER = TypeAdapter(_StrategyManifestPayload)

def _build_indicator_manifest(
    validated: _IndicatorManifestPayload,
) -> IndicatorManifest:
    return IndicatorManifest(
        family="indicators",
        id=validated.id,
        version=validated.version,
        input_names=tuple(validated.input_names),
        param_names=tuple(validated.param_names),
        output_names=tuple(validated.output_names),
        defaults=dict(validated.defaults),
        bar_aligned=True,
    )

def _build_strategy_manifest(
    validated: _StrategyManifestPayload,
) -> StrategyManifest:
    return StrategyManifest(
        family="strategies",
        id=validated.id,
        version=validated.version,
        input_names=tuple(validated.input_names),
        param_names=tuple(validated.param_names),
        output_name=validated.output_name,
        consumes_outputs=tuple(validated.consumes_outputs),
        defaults=dict(validated.defaults),
        owns_portfolio=False,
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
