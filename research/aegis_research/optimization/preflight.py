from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration import OptimizationConfig
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.optimization.candidate_evidence import CANDIDATE_ROLES
from research.aegis_research.run_splits import RunSplitsResult

PREFLIGHT_SCHEMA_VERSION = "optimization_preflight.v1"
PREFLIGHT_PUBLIC_BYTES_PER_ROW = 1024
PREFLIGHT_MAX_EXACT_COMBINE_PARAMS = 100_000
# The runner always returns three representative candidates (best/median/worst),
# which Phase 3 re-runs on every split's held-out set.
HELD_OUT_CANDIDATE_COUNT = len(CANDIDATE_ROLES)


class PreflightError(ValueError):
    def __init__(self, message: str, *, diagnostics: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics)


@dataclass(frozen=True)
class _ParamShape:
    name: str
    value_count: int
    sampled_value_count: int
    level: int
    authored_level: int | None
    has_condition: bool
    hidden: bool
    random_subset: int | float | None


def build_preflight(
    *,
    params: Mapping[str, vbt.Param],
    optimization: OptimizationConfig,
    split_result: RunSplitsResult,
    symbol_count: int,
    has_open_prices: bool,
) -> dict[str, Any]:
    param_shapes = _param_shapes(params)
    theoretical_combinations = _combination_count(param_shapes, sampled=False)
    has_condition = any(shape.has_condition for shape in param_shapes)
    param_sampled_combinations, param_sampled_source, param_sampled_error = _safe_vbt_count(
        params,
        theoretical_combinations=theoretical_combinations,
        optimization=None,
    )
    if param_sampled_combinations is None:
        param_sampled_combinations = _combination_count(param_shapes, sampled=True)
    sampled_combinations, sampled_source, sampled_error = _safe_vbt_count(
        params,
        theoretical_combinations=theoretical_combinations,
        optimization=optimization,
    )
    if sampled_combinations is None:
        sampled_combinations = _sampled_combination_count(
            optimization,
            param_sampled_combinations,
        )
    search_mode = _search_mode(
        optimization,
        sampled_combinations=sampled_combinations,
        executable_combinations=param_sampled_combinations,
    )
    selection_rows = sum(len(split.selection_index) for split in split_result.splits)
    held_out_rows = sum(len(split.held_out_index) for split in split_result.splits)
    total_window_rows = selection_rows + held_out_rows
    split_count = len(split_result.splits)
    set_count = 2
    metric_count = len(PORTFOLIO_METRIC_VALUE_KEYS)
    materialized_frame_count = 4 + int(has_open_prices)
    held_out_candidates = min(HELD_OUT_CANDIDATE_COUNT, sampled_combinations)

    # Phase 1 sweeps the full parameter grid on every split's selection set;
    # Phase 3 re-runs only the representative candidates on every held-out set.
    selection_result_cells = sampled_combinations * split_count * metric_count
    held_out_result_cells = held_out_candidates * split_count * metric_count
    estimated_result_cells = selection_result_cells + held_out_result_cells

    selection_broadcast_cells = (
        sampled_combinations * selection_rows * symbol_count * materialized_frame_count
    )
    held_out_broadcast_cells = (
        held_out_candidates * held_out_rows * symbol_count * materialized_frame_count
    )
    estimated_portfolio_broadcast_cells = selection_broadcast_cells + held_out_broadcast_cells
    estimated_output_cells = max(estimated_result_cells, estimated_portfolio_broadcast_cells)

    # The public artifact carries the three role-tagged candidates, each with
    # per-split selection and held-out metrics.
    candidate_row_count = HELD_OUT_CANDIDATE_COUNT if sampled_combinations else 0
    candidate_metric_rows = candidate_row_count * split_count * set_count
    estimated_public_rows = candidate_row_count + candidate_metric_rows
    estimated_public_artifact_bytes = estimated_public_rows * PREFLIGHT_PUBLIC_BYTES_PER_ROW
    diagnostics = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "search": optimization.search,
        "search_mode": search_mode,
        "param_shapes": [_param_shape_payload(shape) for shape in param_shapes],
        "theoretical_combinations": theoretical_combinations,
        "conditioned_combinations": param_sampled_combinations
        if has_condition
        else theoretical_combinations,
        "param_sampled_combinations": param_sampled_combinations,
        "param_sampled_count_source": param_sampled_source,
        "param_sampled_count_error": param_sampled_error,
        "sampled_combinations": sampled_combinations,
        "sampled_count_source": sampled_source,
        "sampled_count_error": sampled_error,
        "random_subset": optimization.random_subset,
        "seed": optimization.seed,
        "split_count": split_count,
        "set_count": set_count,
        "metric_count": metric_count,
        "selection_rows": selection_rows,
        "held_out_rows": held_out_rows,
        "total_window_rows": total_window_rows,
        "symbol_count": symbol_count,
        "has_open_prices": has_open_prices,
        "materialized_frame_count": materialized_frame_count,
        "held_out_candidates": held_out_candidates,
        "selection_result_cells": selection_result_cells,
        "held_out_result_cells": held_out_result_cells,
        "estimated_result_cells": estimated_result_cells,
        "selection_broadcast_cells": selection_broadcast_cells,
        "held_out_broadcast_cells": held_out_broadcast_cells,
        "estimated_portfolio_broadcast_cells": estimated_portfolio_broadcast_cells,
        "estimated_output_cells": estimated_output_cells,
        "candidate_row_count": candidate_row_count,
        "estimated_public_rows": estimated_public_rows,
        "estimated_public_artifact_bytes": estimated_public_artifact_bytes,
        "limits": {
            "max_estimated_output_cells": optimization.split.max_estimated_output_cells,
            "max_public_artifact_bytes": optimization.split.max_public_artifact_bytes,
        },
        "execute": dict(optimization.execute),
    }
    _raise_if_over_budget(diagnostics, optimization)
    return diagnostics


def _param_shapes(params: Mapping[str, vbt.Param]) -> list[_ParamShape]:
    shapes: list[_ParamShape] = []
    next_implicit_level = 0
    for name, param in params.items():
        value_count = _param_value_count(param)
        random_subset = param.resolve_field("random_subset")
        sampled_value_count = _sampled_value_count(value_count, random_subset)
        authored_level = param.resolve_field("level")
        if authored_level is None:
            level = next_implicit_level
            next_implicit_level += 1
        else:
            level = int(authored_level)
        shapes.append(
            _ParamShape(
                name=name,
                value_count=value_count,
                sampled_value_count=sampled_value_count,
                level=level,
                authored_level=authored_level,
                has_condition=param.resolve_field("condition") is not None,
                hidden=bool(param.resolve_field("hide")),
                random_subset=random_subset,
            )
        )
        if authored_level is not None:
            next_implicit_level = max(next_implicit_level, level + 1)
    return shapes


def _param_value_count(param: vbt.Param) -> int:
    value = param.value
    if isinstance(value, Mapping):
        return len(value)
    if param.resolve_field("is_tuple") or param.resolve_field("is_array_like"):
        return 1
    if isinstance(value, pd.Index | pd.Series):
        return len(value)
    if isinstance(value, str | bytes):
        return 1
    try:
        return len(value)
    except TypeError:
        return 1


def _sampled_value_count(value_count: int, random_subset: int | float | None) -> int:
    if random_subset is None:
        return value_count
    if isinstance(random_subset, float) and 0 < random_subset <= 1:
        return min(value_count, max(1, math.ceil(value_count * random_subset)))
    return min(value_count, max(1, int(random_subset)))


def _combination_count(shapes: list[_ParamShape], *, sampled: bool) -> int:
    level_counts: dict[int, int] = {}
    level_members: dict[int, list[str]] = {}
    for shape in shapes:
        count = shape.sampled_value_count if sampled else shape.value_count
        level_counts.setdefault(shape.level, count)
        level_members.setdefault(shape.level, []).append(shape.name)
        if level_counts[shape.level] != count:
            raise ValueError(
                "optimization params sharing level "
                f"{shape.level!r} must have equal value counts: {level_members[shape.level]}"
            )
    return math.prod(level_counts.values())


def _sampled_combination_count(
    optimization: OptimizationConfig,
    param_sampled_combinations: int,
) -> int:
    if optimization.search == "random":
        if optimization.random_subset is None:
            raise ValueError("optimization.random_subset is required for random search")
        return min(param_sampled_combinations, optimization.random_subset)
    return param_sampled_combinations


def _search_mode(
    optimization: OptimizationConfig,
    *,
    sampled_combinations: int,
    executable_combinations: int,
) -> str:
    """Classify the effective search for evidence; observational, no behavior change.

    ``"exhaustive"`` for non-random search; otherwise ``"random"`` when the random
    subset actually reduces the executable grid, or ``"exhaustive_auto"`` when the
    subset is at least the total executable combinations (the ``min()`` runs every
    combo, e.g. after param locking shrinks the grid).
    """
    if optimization.search != "random":
        return "exhaustive"
    if sampled_combinations < executable_combinations:
        return "random"
    return "exhaustive_auto"


def _safe_vbt_count(
    params: Mapping[str, vbt.Param],
    *,
    theoretical_combinations: int,
    optimization: OptimizationConfig | None,
) -> tuple[int | None, str, str | None]:
    has_condition = any(param.resolve_field("condition") is not None for param in params.values())
    if theoretical_combinations > PREFLIGHT_MAX_EXACT_COMBINE_PARAMS:
        if optimization is not None and optimization.search == "random" and not has_condition:
            if optimization.random_subset is None:
                raise ValueError("optimization.random_subset is required for random search")
            return (
                min(theoretical_combinations, optimization.random_subset),
                "bounded_shape_estimate",
                None,
            )
        if not has_condition:
            return None, "shape_estimate", None
        return (
            None,
            "shape_estimate",
            "conditioned grid exceeds bounded exact combine_params count",
        )

    combine_kwargs: dict[str, Any] = {"build_index": True}
    if optimization is not None and optimization.search == "random":
        if optimization.random_subset is None:
            raise ValueError("optimization.random_subset is required for random search")
        combine_kwargs["random_subset"] = optimization.random_subset
        combine_kwargs["seed"] = optimization.seed
        combine_kwargs["random_sort"] = True
    try:
        _, index = vbt.combine_params(dict(params), **combine_kwargs)
    except Exception as error:  # pragma: no cover - VBT failures are version-specific
        return None, "shape_estimate", str(error)
    return len(index), "vbt.combine_params", None


def _param_shape_payload(shape: _ParamShape) -> dict[str, Any]:
    return {
        "name": shape.name,
        "value_count": shape.value_count,
        "sampled_value_count": shape.sampled_value_count,
        "level": shape.authored_level,
        "effective_level": shape.level,
        "conditioned": shape.has_condition,
        "hidden": shape.hidden,
        "random_subset": shape.random_subset,
    }


def _raise_if_over_budget(
    diagnostics: Mapping[str, Any],
    optimization: OptimizationConfig,
) -> None:
    if diagnostics["estimated_output_cells"] > optimization.split.max_estimated_output_cells:
        raise PreflightError(
            "optimization estimated output cells exceed optimization.split.max_estimated_output_cells",
            diagnostics=diagnostics,
        )
    if (
        optimization.search == "random"
        and optimization.random_subset is not None
        and diagnostics["sampled_combinations"] < optimization.random_subset
    ):
        raise PreflightError(
            "optimization.random_subset exceeds executable parameter combinations",
            diagnostics=diagnostics,
        )
    if (
        diagnostics["estimated_public_artifact_bytes"]
        > optimization.split.max_public_artifact_bytes
    ):
        raise PreflightError(
            "optimization evidence exceeds optimization.split.max_public_artifact_bytes",
            diagnostics=diagnostics,
        )
