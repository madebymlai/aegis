"""Execute continuous Candidate paths and rank their observation-block evidence."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from vectorbtpro import vbt
from vectorbtpro.utils.execution import NoResultsException

from research.aegis_research.configuration import (
    OptimizationConfig,
    RankingConfig,
    ReportConfig,
)
from research.aegis_research.market_data.run_arrays import RunArrays
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.candidate_grid import CandidateGrid
from research.aegis_research.optimization.candidate_paths import (
    CandidatePathError,
    build_development_paths,
)
from research.aegis_research.optimization.observation_blocks import (
    analyze_development_paths,
)
from research.aegis_research.optimization.preflight import OptimizationPreflight
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from research.aegis_research.optimization.source import (
    OPTIMIZATION_PARAM_RESERVED_NAMES,
    OptimizationSource,
)
from research.aegis_research.optimization.window_evaluation import (
    ResolvedBook,
    WindowEvaluator,
)
from research.aegis_research.run_splits import (
    HELD_OUT_SET,
)


class OptimizationRunnerError(ValueError):
    pass


def execute_optimization(
    *,
    arrays: RunArrays,
    source: OptimizationSource,
    optimization: OptimizationConfig,
    book: ResolvedBook,
    report: ReportConfig,
    ranking: RankingConfig,
    metric_registry: FrozenMetricRegistry,
    preflight: OptimizationPreflight,
) -> OptimizationResult:
    """Execute the preflighted continuous replay and observational analysis."""
    _validate_source_param_names(source.params)
    if ranking.metric not in metric_registry:
        raise OptimizationRunnerError(
            f"optimization ranking metric {ranking.metric!r} is not in the "
            f"metric registry: {sorted(metric_registry.ids())}"
        )

    try:
        paths = build_development_paths(
            arrays=arrays,
            source=source,
            optimization=optimization,
            book=book,
            report=report,
            metric_registry=metric_registry,
            min_trades=ranking.min_trades,
            ranking_metric=ranking.metric,
            plan=preflight.plan,
        )
    except CandidatePathError as error:
        raise OptimizationRunnerError(str(error)) from error
    return analyze_development_paths(
        paths,
        preflight.blocks,
        report=report,
        metric_registry=metric_registry,
        ranking_metric=ranking.metric,
    ).result


def _sweep(
    *,
    splitter: vbt.Splitter,
    candidate_metrics: Any,
    apply_input: Any,
    params: Mapping[str, Any],
    set_: str,
    parallel: bool,
) -> CandidateGrid:
    options: dict[str, Any] = {}
    if parallel:
        # Phase 1 distributes the materialised parameter grid across processes:
        # ``mono_n_chunks="auto"`` builds one super-chunk per core that
        # ``engine="pathos"`` runs in parallel (pathos uses dill, so the simulate
        # closure and precomputed store serialize cleanly), while within each chunk
        # the strategy vectorizes its candidates through numpy.
        options["mono_n_chunks"] = "auto"
        # ``join_pool=True`` closes/joins/clears the pathos worker pool after the sweep.
        # vbt defaults this off to reuse a warm pool across repeated sweeps, but a run
        # performs exactly one parallel sweep and the CLI runs one optimization per
        # process, so reuse never applies here; joining tears down the workers
        # deterministically instead of leaking the pool until interpreter exit.
        options["execute_kwargs"] = {"engine": "pathos", "join_pool": True}
    else:
        # Phase 3 (3 candidates x S splits) is too small to amortize per-process
        # serialization, so its single mono-chunk sweeps sequentially in-process.
        options["mono_n_chunks"] = 1
    parameterized = vbt.parameterized(candidate_metrics, merge_func="row_stack", **options)
    try:
        stacked = splitter.apply(
            parameterized,
            apply_input,
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
    return CandidateGrid.from_sweep(stacked)


def _attach_held_out(
    result: OptimizationResult,
    *,
    splitter: vbt.Splitter,
    evaluator: WindowEvaluator,
    param_names: list[str],
    non_executable_rows: int,
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
        candidate_metrics=evaluator.evaluate,
        apply_input=vbt.Rep("range_"),
        params=held_out_params,
        set_=HELD_OUT_SET,
        parallel=False,
    )
    return OptimizationResult(
        best=_with_held_out(result.best, held_out_grid),
        median=_with_held_out(result.median, held_out_grid),
        worst=_with_held_out(result.worst, held_out_grid),
        excluded_degenerate=result.excluded_degenerate,
        excluded_invalid=result.excluded_invalid,
        total_candidates=result.total_candidates,
        non_executable_rows=non_executable_rows,
        omnibus=result.omnibus,
    )


def _with_held_out(
    candidate: EvaluatedCandidate,
    held_out_grid: CandidateGrid,
) -> EvaluatedCandidate:
    key = tuple(candidate.params[name] for name in held_out_grid.param_levels)
    held_out = held_out_grid.split_metrics(key)
    return dataclasses.replace(candidate, held_out_metrics=held_out)


def _validate_source_param_names(params: Mapping[str, vbt.Param]) -> None:
    reserved = sorted(set(params) & OPTIMIZATION_PARAM_RESERVED_NAMES)
    if reserved:
        raise OptimizationRunnerError(
            f"optimization param names {reserved} are reserved for Aegis/VBT result "
            "coordinates; choose distinct parameter names"
        )
