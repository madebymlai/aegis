from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration.schema import OptimizationConfig
from research.aegis_research.run_splits import RunSplitsResult

PREFLIGHT_SCHEMA_VERSION = "optimization_preflight.v1"
PREFLIGHT_PUBLIC_BYTES_PER_ROW = 1024


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
    param_sampled_combinations = _combination_count(param_shapes, sampled=True)
    sampled_combinations = _sampled_combination_count(
        optimization,
        param_sampled_combinations,
    )
    selection_rows = sum(len(split.selection_index) for split in split_result.splits)
    held_out_rows = sum(len(split.held_out_index) for split in split_result.splits)
    total_window_rows = selection_rows + held_out_rows
    set_count = 2
    materialized_frame_count = 4 + int(has_open_prices)
    estimated_result_cells = sampled_combinations * len(split_result.splits) * set_count
    estimated_portfolio_broadcast_cells = (
        sampled_combinations * total_window_rows * symbol_count * materialized_frame_count
    )
    estimated_output_cells = max(estimated_result_cells, estimated_portfolio_broadcast_cells)
    retained_selection_grid_rows = sampled_combinations * len(split_result.splits)
    retained_grid_rows = retained_selection_grid_rows
    if optimization.evidence.return_grid == "all":
        retained_grid_rows *= set_count
    selected_held_out_rows = len(split_result.splits)
    estimated_public_rows = retained_grid_rows + selected_held_out_rows
    estimated_public_artifact_bytes = (
        estimated_public_rows * PREFLIGHT_PUBLIC_BYTES_PER_ROW
    )
    diagnostics = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "search": optimization.search,
        "return_grid": optimization.evidence.return_grid,
        "param_shapes": [_param_shape_payload(shape) for shape in param_shapes],
        "theoretical_combinations": theoretical_combinations,
        "conditioned_combinations": (
            None if any(shape.has_condition for shape in param_shapes) else theoretical_combinations
        ),
        "param_sampled_combinations": param_sampled_combinations,
        "sampled_combinations": sampled_combinations,
        "random_subset": optimization.random_subset,
        "seed": optimization.seed,
        "split_count": len(split_result.splits),
        "set_count": set_count,
        "selection_rows": selection_rows,
        "held_out_rows": held_out_rows,
        "total_window_rows": total_window_rows,
        "symbol_count": symbol_count,
        "has_open_prices": has_open_prices,
        "materialized_frame_count": materialized_frame_count,
        "estimated_result_cells": estimated_result_cells,
        "estimated_portfolio_broadcast_cells": estimated_portfolio_broadcast_cells,
        "estimated_output_cells": estimated_output_cells,
        "retained_selection_grid_rows": retained_selection_grid_rows,
        "retained_grid_rows": retained_grid_rows,
        "selected_held_out_rows": selected_held_out_rows,
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
    if diagnostics["estimated_public_artifact_bytes"] > optimization.split.max_public_artifact_bytes:
        raise PreflightError(
            "optimization evidence exceeds optimization.split.max_public_artifact_bytes",
            diagnostics=diagnostics,
        )
