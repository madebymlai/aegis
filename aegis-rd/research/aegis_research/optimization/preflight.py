"""Pre-execution geometry for continuous Candidate replay and block analysis."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration import OptimizationConfig
from research.aegis_research.optimization.candidate_paths import (
    CandidatePathError,
    DevelopmentPlan,
    plan_development,
)
from research.aegis_research.optimization.observation_blocks import (
    ObservationBlockError,
    ObservationBlocks,
)
from research.aegis_research.optimization.source import OptimizationSource

PREFLIGHT_SCHEMA_VERSION = "optimization_preflight.v2"


class PreflightError(ValueError):
    def __init__(self, message: str, *, diagnostics: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics)


@dataclass(frozen=True)
class OptimizationPreflight:
    """Diagnostics and the exact materialized geometry consumed by execution."""

    diagnostics: Mapping[str, Any]
    plan: DevelopmentPlan
    blocks: ObservationBlocks


def build_preflight(
    *,
    source: OptimizationSource,
    optimization: OptimizationConfig,
    index: pd.Index,
    symbol_count: int,
    metric_count: int,
    has_open_prices: bool,
) -> OptimizationPreflight:
    """Resolve all Candidate/block geometry before Indicator or Portfolio execution."""
    diagnostics: dict[str, Any] = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "search": optimization.search,
        "loaded_rows": len(index),
        "observation_block_bars": optimization.observation_block_bars,
        "symbol_count": symbol_count,
        "metric_count": metric_count,
        "has_open_prices": has_open_prices,
    }
    try:
        plan = plan_development(
            source=source,
            optimization=optimization,
            row_count=len(index),
        )
    except CandidatePathError as error:
        raise PreflightError(str(error), diagnostics=diagnostics) from error

    scored_start = plan.lookbacks.scored_start
    scored_rows = len(index) - scored_start
    theoretical_combinations = _theoretical_combination_count(source.params)
    diagnostics.update(
        {
            "theoretical_combinations": theoretical_combinations,
            "sampled_combinations": plan.candidates.count,
            "sampled_count_source": "materialized_grid",
            "search_mode": _search_mode(
                optimization,
                plan.candidates.count,
                theoretical_combinations,
            ),
            "candidate_param_names": list(plan.candidates.param_names),
            "candidate_warmup_bars": list(plan.lookbacks.candidate_warmup_bars),
            "derived_warmup_rows": plan.lookbacks.resolved_warmup_bars,
            "scored_start": scored_start,
            "scored_rows": scored_rows,
        }
    )
    try:
        blocks = ObservationBlocks.resolve_scored_interval(
            index,
            scored_start=scored_start,
            block_bars=optimization.observation_block_bars,
        )
    except ObservationBlockError as error:
        raise PreflightError(str(error), diagnostics=diagnostics) from error

    materialized_frame_count = 4 + int(has_open_prices)
    candidate_count = plan.candidates.count
    block_count = len(blocks.bounds)
    diagnostics.update(
        {
            "observation_block_count": block_count,
            "observation_block_bounds": [list(bounds) for bounds in blocks.bounds],
            "observation_block_labels": list(blocks.labels),
            "materialized_frame_count": materialized_frame_count,
            "peak_candidate_batch_count": candidate_count,
            "peak_candidate_batch_rows": candidate_count * len(index),
            "peak_candidate_batch_cells": (
                candidate_count * len(index) * symbol_count * materialized_frame_count
            ),
            "replay_candidate_rows": candidate_count * scored_rows,
            "observation_metric_cells": candidate_count * block_count * metric_count,
        }
    )
    return OptimizationPreflight(
        diagnostics=diagnostics,
        plan=plan,
        blocks=blocks,
    )


def _theoretical_combination_count(params: Mapping[str, vbt.Param]) -> int:
    level_counts: dict[int, int] = {}
    next_implicit_level = 0
    for param in params.values():
        authored_level = param.resolve_field("level")
        if authored_level is None:
            level = next_implicit_level
            next_implicit_level += 1
        else:
            level = int(authored_level)
            next_implicit_level = max(next_implicit_level, level + 1)
        count = _param_value_count(param)
        previous = level_counts.setdefault(level, count)
        if previous != count:
            raise PreflightError(
                f"optimization params sharing level {level!r} must have equal value counts",
                diagnostics={"schema_version": PREFLIGHT_SCHEMA_VERSION},
            )
    return math.prod(level_counts.values())


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


def _search_mode(
    optimization: OptimizationConfig,
    sampled_count: int,
    theoretical_count: int,
) -> str:
    if optimization.search != "random":
        return "exhaustive"
    return "random" if sampled_count < theoretical_count else "exhaustive_auto"


__all__ = [
    "PREFLIGHT_SCHEMA_VERSION",
    "OptimizationPreflight",
    "PreflightError",
    "build_preflight",
]
