"""Run Config validation — whole-tree coordinator.

With ``RunConfig`` as a whole-tree pydantic dataclass, one
``TypeAdapter(RunConfig).validate_python(raw)`` validates the entire tree
and accumulates all structural errors natively.

The coordinator owns:
- Top-level prepass: ``schema_version`` presence/version check,
  ``split.method`` inspection.
- Whole-tree pydantic ``validate_python`` call + error-to-issue adapter.
- Name check, data-source whitelist, lock shape check.
- One unconditional call to the registry cross-checks module.

Returns ``(RunConfig | None, list[ConfigValidationIssue])`` so the caller
can inspect whether pydantic construction succeeded while still seeing all
accumulated issues.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter, ValidationError

from research.aegis_research.configuration.field_types import IDENTIFIER_RE
from research.aegis_research.configuration.schema import (
    CONFIG_SCHEMA_VERSION,
    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
    LOCK_ROLES,
    ConfigValidationIssue,
    DataConfig,
    Lock,
    RunConfig,
)
from research.aegis_research.metrics import FrozenMetricRegistry

if TYPE_CHECKING:
    from research.aegis_research.component_registry import FrozenComponentRegistry

# Built once at import: TypeAdapter construction compiles the whole-tree core
# schema, which is too expensive to repeat per validation call.
_RUN_CONFIG_ADAPTER = TypeAdapter(RunConfig)


def validate_run_config(
    raw: dict[str, Any],
    *,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> tuple[RunConfig | None, list[ConfigValidationIssue]]:
    """Whole-tree run config validation with accumulated issues.

    Always returns the full issues list even when pydantic construction fails,
    so structural and registry errors are co-reported.
    """
    if not isinstance(raw, dict):
        return None, [ConfigValidationIssue("$", "run config must be a mapping")]

    issues: list[ConfigValidationIssue] = []

    # ── Prepass: tombstones, schema_version, removed fields, split method ──
    _prepass_raw_config(raw, issues)

    # ── Whole-tree pydantic validation ────────────────────────────────────
    config = None
    try:
        config = _RUN_CONFIG_ADAPTER.validate_python(raw)
    except ValidationError as e:
        issues.extend(_validation_error_to_issues_whole_tree(e))

    # ── Post-pydantic checks (need runtime state) ─────────────────────────
    if config is not None:
        _post_validate_name(config.name, issues)
        _post_validate_data_source(config.data, issues)
        _check_lock_shape(config.lock, raw.get("lock"), issues)

    # ── Registry cross-checks (always run, even when pydantic failed) ─────
    from research.aegis_research.configuration.cross_checks import cross_check_registries

    registry_input = config if config is not None else raw
    issues.extend(
        cross_check_registries(
            registry_input,
            component_registry=component_registry,
            metric_registry=metric_registry,
        )
    )

    return config, issues


# ── prepass ──────────────────────────────────────────────────────────────────

def _prepass_raw_config(raw: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    """Raw-dict checks that must run before (or regardless of) pydantic validation.

    Removed legacy fields carry no tombstones: they fall through to
    ``extra="forbid"``'s unknown-key rejection like any field that never existed.
    """
    # schema_version presence + version check
    if "schema_version" not in raw or raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        issues.append(
            ConfigValidationIssue("schema_version", f"must be {CONFIG_SCHEMA_VERSION}")
        )

    # Optimization required (forward optimization contract)
    if "optimization" not in raw:
        issues.append(
            ConfigValidationIssue(
                "optimization", FORWARD_OPTIMIZATION_REQUIRED_MESSAGE
            )
        )

    # Split-method prepass (VBT introspection, produces dotted paths)
    optimization_raw = raw.get("optimization")
    if isinstance(optimization_raw, dict):
        split_raw = optimization_raw.get("split")
        if isinstance(split_raw, dict):
            from research.aegis_research.run_splits import validate_run_split_config
            validate_run_split_config(split_raw, issues, path="optimization.split")


# ── error adapter ────────────────────────────────────────────────────────────

def _validation_error_to_issues_whole_tree(
    error: ValidationError,
) -> list[ConfigValidationIssue]:
    """Map every pydantic ``ValidationError`` entry to a ``ConfigValidationIssue``.

    ``loc`` is a full-path tuple across the whole tree (e.g.
    ``('portfolio', 'gross_cap')`` or ``('indicators', 0, 'id')``).
    Int elements use bracket notation (``[i]``); string elements are dotted.
    The pydantic ``msg`` is taken verbatim.
    """
    issues: list[ConfigValidationIssue] = []
    for entry in error.errors():
        loc = entry["loc"]
        if not loc:
            path = "$"
        else:
            parts: list[str] = []
            for part in loc:
                if isinstance(part, int):
                    parts.append(f"[{part}]")
                else:
                    if parts:
                        parts.append(".")
                    parts.append(str(part))
            path = "".join(parts)
        issues.append(ConfigValidationIssue(path, entry["msg"]))
    return issues


# ── post-pydantic checks ────────────────────────────────────────────────────

def _post_validate_name(
    name: str,
    issues: list[ConfigValidationIssue],
) -> None:
    if not IDENTIFIER_RE.fullmatch(name) or name in {".", ".."}:
        issues.append(
            ConfigValidationIssue(
                "name",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )


def _post_validate_data_source(
    data: DataConfig,
    issues: list[ConfigValidationIssue],
) -> None:
    """Source whitelist (post-pydantic: needs runtime state)."""
    from research.aegis_research.market_data.sources import (
        LOCAL_DATA_SOURCES,
        remote_data_sources,
    )

    supported = LOCAL_DATA_SOURCES | remote_data_sources()
    if data.source not in supported:
        issues.append(
            ConfigValidationIssue(
                "data.source", f"must be one of {sorted(supported)}"
            )
        )


def _check_lock_shape(
    lock: Lock | None,
    lock_raw: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    """Reject empty run_id and unknown role keywords (shape check, not registry check)."""
    if lock is None:
        return
    was_handle = isinstance(lock_raw, str)
    if not lock.run_id:
        issues.append(ConfigValidationIssue("lock", "run_id must not be empty"))
    if was_handle and lock.candidate_id not in LOCK_ROLES:
        roles_label = ", ".join(LOCK_ROLES)
        issues.append(
            ConfigValidationIssue(
                "lock",
                f"role must be one of: {roles_label} (got {lock.candidate_id!r})",
            )
        )
