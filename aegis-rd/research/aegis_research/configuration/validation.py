"""Run Config validation — whole-tree coordinator.

With ``RunConfig`` as a whole-tree pydantic dataclass, one
``TypeAdapter(RunConfig).validate_python(raw)`` validates the entire tree
and accumulates all structural errors natively.

The coordinator owns the whole-tree pydantic call, its error-to-issue adapter,
the typed whole-config checks, and registry cross-check orchestration.

Returns ``(RunConfig | None, list[ConfigValidationIssue])`` so the caller
can inspect whether pydantic construction succeeded while still seeing all
accumulated issues.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError

from research.aegis_research.component_registry import FrozenComponentRegistry
from research.aegis_research.configuration.cross_checks import cross_check_registries
from research.aegis_research.configuration.schema import ConfigValidationIssue, RunConfig
from research.aegis_research.metrics import FrozenMetricRegistry

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

    # ── Whole-tree pydantic validation ────────────────────────────────────
    config = None
    try:
        config = _RUN_CONFIG_ADAPTER.validate_python(raw)
    except ValidationError as e:
        issues.extend(_validation_error_to_issues_whole_tree(e))

    # ── Post-pydantic checks (need runtime state) ─────────────────────────
    if config is not None:
        _check_portfolio_band_overrides(config, issues)

    # ── Registry cross-checks (always run, even when pydantic failed) ─────
    registry_input = config if config is not None else raw
    issues.extend(
        cross_check_registries(
            registry_input,
            component_registry=component_registry,
            metric_registry=metric_registry,
        )
    )

    return config, issues


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
