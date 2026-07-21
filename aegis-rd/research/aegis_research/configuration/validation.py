"""Run Config validation — whole-tree coordinator.

With ``RunConfig`` as a whole-tree pydantic dataclass, one
``TypeAdapter(RunConfig).validate_python(raw)`` validates the entire tree
and accumulates all structural errors natively.

The coordinator owns:
- Top-level prepass: ``schema_version`` presence/version check,
  ``split.method`` inspection.
- Whole-tree pydantic ``validate_python`` call + error-to-issue adapter.
- Name check and lock shape check.
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
    LOCK_ROLES,
    PREPASS_CONST_FIELDS,
    PREPASS_REQUIRED_FIELDS,
    ConfigValidationIssue,
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

    # ── Prepass: tombstones, schema_version, and removed fields ──
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
        _check_lock_shape(config.lock, raw.get("lock"), issues)
        _check_portfolio_band_overrides(config, issues)

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
    # Forward-contract overlay: const + required top-level fields. These checks
    # read the same PREPASS_* constants that drive the config-schema guide, so
    # what ``aerd run`` enforces here cannot fork from what the guide documents
    # (ADR-0019).
    for field_name, const_value in PREPASS_CONST_FIELDS.items():
        if raw.get(field_name) != const_value:
            issues.append(ConfigValidationIssue(field_name, f"must be {const_value}"))

    for field_name, required_message in PREPASS_REQUIRED_FIELDS.items():
        if field_name not in raw:
            issues.append(ConfigValidationIssue(field_name, required_message))

# ── error adapter ────────────────────────────────────────────────────────────

def _validation_error_to_issues_whole_tree(
    error: ValidationError,
) -> list[ConfigValidationIssue]:
    """Map every pydantic ``ValidationError`` entry to a ``ConfigValidationIssue``.

    ``loc`` is a full-path tuple across the whole tree (e.g.
    ``('portfolio', 'direction')`` or ``('indicators', 0, 'id')``).
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


def _check_portfolio_band_overrides(
    config: RunConfig,
    issues: list[ConfigValidationIssue],
) -> None:
    if not config.portfolio.band_overrides:
        return
    allowed = set(config.data.instruments) | set(config.data.futures)
    unknown = sorted(set(config.portfolio.band_overrides) - allowed)
    if unknown:
        issues.append(
            ConfigValidationIssue(
                "portfolio.band_overrides",
                "unknown tradeable keys "
                f"{unknown}; expected keys from data.instruments or data.futures: "
                f"{sorted(allowed)}",
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
