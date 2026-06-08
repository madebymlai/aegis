"""Optimization configuration validation.

Validates the ``optimization`` block: search policy (grid/random), the nested run split
(walk-forward windows, JSON-safe params, no reserved set_labels), the random-subset/seed
determinism contract, and the execute passthrough (reserved keys owned by Aegis ranking
must not leak in).
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.configuration.schema import (
    OPTIMIZATION_SEARCH_POLICIES,
    ConfigValidationIssue,
    OptimizationConfig,
    RunSplitConfig,
)
from research.aegis_research.configuration.validation.base import (
    _optional_int,
    _require_str,
    _validate_json_like,
    _validate_known_keys,
    _validate_no_run_executable_keys,
)
from research.aegis_research.run_splits import validate_run_split_config

OPTIMIZATION_EXECUTE_RESERVED_KEYS = frozenset(
    {
        "random_subset",
        "seed",
        "merge_func",
        "raise_no_results",
        "filter_results",
    }
)


def _validate_optimization(raw: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    if "optimization" not in raw:
        return
    optimization = raw.get("optimization")
    if not isinstance(optimization, dict):
        issues.append(ConfigValidationIssue("optimization", "must be a mapping"))
        return

    _validate_known_keys(
        "optimization",
        optimization,
        set(OptimizationConfig.__dataclass_fields__),
        issues,
    )
    if _require_str("optimization.search", optimization, issues):
        search = optimization["search"]
        if search not in OPTIMIZATION_SEARCH_POLICIES:
            issues.append(
                ConfigValidationIssue(
                    "optimization.search",
                    f"must be one of {sorted(OPTIMIZATION_SEARCH_POLICIES)}",
                )
            )
    else:
        search = None

    _validate_optimization_split(optimization, issues)
    _validate_optimization_random_policy(optimization, issues, search=search)
    _optional_int("optimization.seed", optimization, issues, minimum=0, allow_none=True)
    _validate_optimization_execute(optimization.get("execute", {}), issues)


def _validate_optimization_split(
    optimization: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    if "split" not in optimization:
        issues.append(ConfigValidationIssue("optimization.split", "is required for optimization"))
        return
    split = optimization["split"]
    if not isinstance(split, dict):
        issues.append(ConfigValidationIssue("optimization.split", "must be a mapping"))
        return
    _validate_known_keys(
        "optimization.split",
        split,
        set(RunSplitConfig.__dataclass_fields__),
        issues,
    )
    _validate_run_split(split, issues, path="optimization.split")


def _validate_run_split(
    split: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    path: str = "split",
) -> None:
    _optional_int(f"{path}.max_splits", split, issues, positive=True)
    _optional_int(f"{path}.max_estimated_output_cells", split, issues, positive=True)
    _optional_int(f"{path}.max_public_artifact_bytes", split, issues, positive=True)

    params = split.get("params", {})
    if not isinstance(params, dict):
        issues.append(ConfigValidationIssue(f"{path}.params", "must be a mapping"))
    else:
        _validate_json_like(f"{path}.params", params, issues)
        _validate_no_run_executable_keys(f"{path}.params", params, issues)
        if "set_labels" in params:
            issues.append(
                ConfigValidationIssue(
                    f"{path}.params.set_labels",
                    "set roles are owned by Aegis and assigned positionally "
                    "(set 0 selection, set 1 held_out); set_labels is not configurable",
                )
            )
    validate_run_split_config(split, issues, path=path)


def _validate_optimization_random_policy(
    optimization: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    search: str | None,
) -> None:
    random_subset = optimization.get("random_subset")
    if "random_subset" in optimization:
        _optional_int(
            "optimization.random_subset",
            optimization,
            issues,
            positive=True,
            allow_none=True,
        )
    if search == "random" and random_subset is None:
        issues.append(
            ConfigValidationIssue(
                "optimization.random_subset",
                "is required when optimization.search is 'random'",
            )
        )
    if search == "random" and optimization.get("seed") is None:
        issues.append(
            ConfigValidationIssue(
                "optimization.seed",
                "is required when optimization.search is 'random' so sampled evidence is deterministic",
            )
        )
    if search == "grid" and random_subset is not None:
        issues.append(
            ConfigValidationIssue(
                "optimization.random_subset",
                "only valid when optimization.search is 'random'",
            )
        )


def _validate_optimization_execute(value: Any, issues: list[ConfigValidationIssue]) -> None:
    path = "optimization.execute"
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_json_like(path, value, issues)
    _validate_no_run_executable_keys(path, value, issues)
    reserved = sorted(set(value) & OPTIMIZATION_EXECUTE_RESERVED_KEYS)
    if reserved:
        issues.append(
            ConfigValidationIssue(
                path,
                f"reserved keys {reserved} are owned by optimization.search / "
                "Aegis ranking policy and must not appear "
                "under optimization.execute",
            )
        )
