"""Optimization runner: two-phase ``Splitter.apply`` + ``vbt.parameterized``.

Phase 1 sweeps the full parameter grid on every split's *selection* set,
producing a tidy grid (one row per candidate per split, one column per metric).
Phase 2 ranks candidates globally and returns three representative candidates
(best / median / worst). Phase 3 re-runs those three on every split's
*held-out* set and attaches the held-out metrics.

A single ``Splitter`` instance is constructed from the run config and reused for
both phases so selection and held-out share identical split boundaries. The
splitter is built with explicit ``set_labels=["selection", "held_out"]`` so that
``set_=`` resolves by role rather than VBT's generic positional labels.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from typing import Any

import pandas as pd
from vectorbtpro import vbt
from vectorbtpro.utils.execution import NoResultsException

from research.aegis_research.configuration.schema import (
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
)
from research.aegis_research.metrics.accessors import (
    METRIC_INDEX_NAME,
    central_metrics_from_accessors,
)
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.optimization.ranking import (
    SPLIT_LEVEL,
    EvaluatedCandidate,
    OptimizationResult,
    select_representative_candidates,
)
from research.aegis_research.optimization.source import (
    OPTIMIZATION_PARAM_RESERVED_NAMES,
    OptimizationSource,
)
from research.aegis_research.portfolios import simulate_portfolio_batch

SELECTION_SET = "selection"
HELD_OUT_SET = "held_out"
SET_LABELS = [SELECTION_SET, HELD_OUT_SET]


class OptimizationRunnerError(ValueError):
    pass


def execute_optimization(
    *,
    close: pd.DataFrame,
    source: OptimizationSource,
    optimization: OptimizationConfig,
    portfolio: PortfolioConfig,
    report: ReportConfig,
    ranking: RankingConfig,
) -> OptimizationResult:
    _validate_source_param_names(source.params)
    if ranking.metric not in PORTFOLIO_METRIC_VALUE_KEYS:
        raise OptimizationRunnerError(
            f"optimization ranking metric {ranking.metric!r} is not in the central "
            f"portfolio metric catalog: {sorted(PORTFOLIO_METRIC_VALUE_KEYS)}"
        )

    splitter = _build_splitter(close.index, optimization)
    candidate_metrics = _build_candidate_metrics(
        source=source, portfolio=portfolio, report=report
    )

    selection_grid = _sweep(
        splitter=splitter,
        candidate_metrics=candidate_metrics,
        close=close,
        params=dict(source.params),
        set_=SELECTION_SET,
        random=_random_options(optimization),
    )
    result = select_representative_candidates(
        selection_grid, metric=ranking.metric, min_weight=ranking.min_weight
    )

    param_names = [name for name in selection_grid.index.names if name != SPLIT_LEVEL]
    return _attach_held_out(
        result,
        splitter=splitter,
        candidate_metrics=candidate_metrics,
        close=close,
        param_names=param_names,
    )


def _build_splitter(index: pd.Index, optimization: OptimizationConfig) -> vbt.Splitter:
    method = optimization.split.method
    factory = getattr(vbt.Splitter, method, None)
    if not callable(factory):
        raise OptimizationRunnerError(f"unknown VBT splitter method: {method!r}")
    return factory(index, set_labels=SET_LABELS, **dict(optimization.split.params))


def _build_candidate_metrics(
    *,
    source: OptimizationSource,
    portfolio: PortfolioConfig,
    report: ReportConfig,
) -> Any:
    pipeline = source.pipeline

    def candidate_metrics(close_slice: pd.DataFrame, **params: Any) -> Any:
        combo_lists = {name: [value] for name, value in params.items()}
        wide_allocations = pipeline(close_slice, 1, **combo_lists)
        if wide_allocations is vbt.NoResult:
            return vbt.NoResult
        n_symbols = len(close_slice.columns)
        if n_symbols == 0 or len(wide_allocations.columns) // n_symbols < 1:
            return vbt.NoResult
        result = simulate_portfolio_batch(
            close_slice,
            wide_allocations,
            portfolio,
            market_index=close_slice.index,
            compute_diagnostics=False,
        )
        return central_metrics_from_accessors(result.portfolio, report)

    return candidate_metrics


def _sweep(
    *,
    splitter: vbt.Splitter,
    candidate_metrics: Any,
    close: pd.DataFrame,
    params: Mapping[str, Any],
    set_: str,
    random: Mapping[str, Any],
) -> pd.DataFrame:
    parameterized = vbt.parameterized(candidate_metrics, merge_func="row_stack", **dict(random))
    try:
        stacked = splitter.apply(
            parameterized,
            vbt.Takeable(close),
            set_=set_,
            merge_func="row_stack",
            **dict(params),
        )
    except NoResultsException as error:
        raise OptimizationRunnerError(
            "optimization pipeline produced no usable results across the requested "
            "parameter grid; every sampled combination returned vbt.NoResult or was "
            "filtered out — return finite metrics from invalid combinations instead so "
            "they remain visible in evidence"
        ) from error
    return _tidy_grid(stacked)


def _tidy_grid(stacked: Any) -> pd.DataFrame:
    if not isinstance(stacked, pd.Series) or not isinstance(stacked.index, pd.MultiIndex):
        raise OptimizationRunnerError(
            "optimization sweep must row-stack into a Series indexed by split, "
            f"parameters, and metric; got {type(stacked).__name__}"
        )
    tidy = stacked.unstack(level=METRIC_INDEX_NAME)
    tidy.columns.name = None
    return tidy


def _attach_held_out(
    result: OptimizationResult,
    *,
    splitter: vbt.Splitter,
    candidate_metrics: Any,
    close: pd.DataFrame,
    param_names: list[str],
) -> OptimizationResult:
    candidates = [result.best, result.median, result.worst]
    unique_params: list[dict[str, Any]] = []
    for candidate in candidates:
        params = dict(candidate.params)
        if params not in unique_params:
            unique_params.append(params)

    held_out_params = {
        name: vbt.Param([params[name] for params in unique_params], level=0)
        for name in param_names
    }
    held_out_grid = _sweep(
        splitter=splitter,
        candidate_metrics=candidate_metrics,
        close=close,
        params=held_out_params,
        set_=HELD_OUT_SET,
        random={},
    )
    return OptimizationResult(
        best=_with_held_out(result.best, held_out_grid, param_names),
        median=_with_held_out(result.median, held_out_grid, param_names),
        worst=_with_held_out(result.worst, held_out_grid, param_names),
    )


def _with_held_out(
    candidate: EvaluatedCandidate,
    held_out_grid: pd.DataFrame,
    param_names: list[str],
) -> EvaluatedCandidate:
    held_out = _candidate_split_metrics(held_out_grid, candidate.params, param_names)
    return dataclasses.replace(candidate, held_out_metrics=held_out)


def _candidate_split_metrics(
    grid: pd.DataFrame,
    params: Mapping[str, Any],
    param_names: list[str],
) -> dict[Any, dict[str, float | None]]:
    selector = pd.Series(True, index=grid.index)
    for name in param_names:
        selector &= grid.index.get_level_values(name) == params[name]
    rows = grid[selector.to_numpy()]
    metrics: dict[Any, dict[str, float | None]] = {}
    split_labels = rows.index.get_level_values(SPLIT_LEVEL)
    for split_label, (_, row) in zip(split_labels, rows.iterrows(), strict=True):
        metrics[split_label] = {col: _optional_float(row[col]) for col in grid.columns}
    return metrics


def _random_options(optimization: OptimizationConfig) -> dict[str, Any]:
    if optimization.search != "random":
        return {}
    if optimization.random_subset is None:
        raise OptimizationRunnerError(
            "optimization.random_subset is required when optimization.search is 'random'"
        )
    if optimization.seed is None:
        raise OptimizationRunnerError(
            "optimization.seed is required when optimization.search is 'random' so the "
            "sampled selection grid is deterministic"
        )
    return {"random_subset": optimization.random_subset, "seed": optimization.seed}


def _validate_source_param_names(params: Mapping[str, vbt.Param]) -> None:
    reserved = sorted(set(params) & OPTIMIZATION_PARAM_RESERVED_NAMES)
    if reserved:
        raise OptimizationRunnerError(
            f"optimization param names {reserved} are reserved for Aegis/VBT result "
            "coordinates; choose distinct parameter names"
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) else number
