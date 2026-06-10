"""Optimization runner: two-phase ``Splitter.apply`` + ``vbt.parameterized``.

The selection phase runs in two stages so indicator warmup can use the full
available history. The candidate set is materialised once up front (seeded
``combine_params``); each indicator's wide callable runs once over the **full**
series into a candidate-major store (stage 1, ``precompute``); candidates with an
entirely non-finite full-history block for any indicator output are marked invalid;
then Phase 1 sweeps every split's *selection* set running only stage 2
(``simulate``), slicing the precomputed store to each window via the splitter's
``range_`` template — producing a Candidate Grid (one row per candidate per split, one
column per metric). Phase 2 ranks candidates globally and returns three
representative candidates (best / median / worst). Phase 3 re-runs those three on
every split's *held-out* set and attaches the held-out metrics, again slicing the
full-series indicator store instead of recomputing indicators on bare held-out
slices.

The runner constructs no ``Splitter`` of its own: it consumes the single one
built by run_splits from ``RunSplitsResult.splitter`` (ADR-0018) and reuses it
for both phases, so selection and held-out share identical split boundaries and
``set_=`` resolves by the role labels run_splits imposed at construction.
"""

from __future__ import annotations

import dataclasses
import multiprocessing
from collections.abc import Callable, Mapping, MutableSequence
from typing import Any

import numpy as np
import pandas as pd
from vectorbtpro import vbt
from vectorbtpro.utils.execution import NoResultsException

from research.aegis_research.configuration import (
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
)
from research.aegis_research.metrics.accessors import (
    central_metrics_from_grouped_accessors,
)
from research.aegis_research.metrics.contracts import ExtractorSpec
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.candidate_grid import CandidateGrid
from research.aegis_research.optimization.candidate_validity import (
    classify_candidates,
    invalid_candidate_positions,
    invalid_candidates,
)
from research.aegis_research.optimization.precompute import (
    CandidateKey,
    WideIndicatorPrecompute,
    candidate_keys,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
    select_representative_candidates,
)
from research.aegis_research.optimization.source import (
    OPTIMIZATION_PARAM_RESERVED_NAMES,
    OptimizationSource,
)
from research.aegis_research.portfolios import simulate_portfolio_batch
from research.aegis_research.run_splits import (
    HELD_OUT_SET,
    SELECTION_SET,
    RunSplitsResult,
)


class OptimizationRunnerError(ValueError):
    pass


def execute_optimization(
    *,
    close: pd.DataFrame,
    open_: pd.DataFrame,
    source: OptimizationSource,
    optimization: OptimizationConfig,
    portfolio: PortfolioConfig,
    report: ReportConfig,
    ranking: RankingConfig,
    metric_registry: FrozenMetricRegistry,
    split_result: RunSplitsResult,
) -> OptimizationResult:
    _validate_source_param_names(source.params)
    if ranking.metric not in metric_registry:
        raise OptimizationRunnerError(
            f"optimization ranking metric {ranking.metric!r} is not in the "
            f"metric registry: {sorted(metric_registry.ids())}"
        )

    # The registry record is the single home for each Metric's definition and its
    # extractor; the sweep is handed a plain extractor mapping (catalog order) so
    # the dill-serialised Phase-1 closure carries no registry/proxy machinery.
    extractors = dict(metric_registry.extractors)
    splitter = split_result.splitter

    # Stage 0: materialise the sampled candidate set once, deterministically, and
    # feed the same set to BOTH the precompute and the selection sweep.
    sampled_lists = _materialize_candidates(source.params, optimization)
    n_candidates = len(next(iter(sampled_lists.values()))) if sampled_lists else 0
    sampled_params = {
        name: vbt.Param(values, level=0) for name, values in sampled_lists.items()
    }

    # Stage 1: run each indicator's wide callable once over the full series.
    sampled_candidate_keys = candidate_keys(sampled_lists)
    store = source.precompute(close, n_candidates, **sampled_lists)
    invalid_candidate_keys = invalid_candidates(
        store, sampled_candidate_keys
    )

    # Phase 1: stage-2 sweep slicing the precomputed store to each selection window.
    selection_metrics = _build_precomputed_window_metrics(
        source=source,
        portfolio=portfolio,
        report=report,
        close=close,
        open_=open_,
        store=store,
        invalid_candidate_keys=invalid_candidate_keys,
        extractors=extractors,
    )
    selection_grid = _sweep(
        splitter=splitter,
        candidate_metrics=selection_metrics,
        apply_input=vbt.Rep("range_"),
        params=sampled_params,
        set_=SELECTION_SET,
        parallel=True,
    )
    verdicts = classify_candidates(
        selection_grid,
        invalid_keys=invalid_candidate_keys,
        min_trades=ranking.min_trades,
        metric=ranking.metric,
    )
    result = select_representative_candidates(
        selection_grid,
        verdicts,
        metric=ranking.metric,
        min_weight=ranking.min_weight,
    )

    param_names = selection_grid.param_levels
    # Collect non-executable-row counts from the selection sweep.
    selection_held_counts: list[int] = getattr(selection_metrics, "held_counts", [])
    return _attach_held_out(
        result,
        splitter=splitter,
        source=source,
        portfolio=portfolio,
        report=report,
        close=close,
        open_=open_,
        store=store,
        param_names=param_names,
        invalid_candidate_keys=invalid_candidate_keys,
        extractors=extractors,
        selection_held_counts=selection_held_counts,
    )


def _build_precomputed_window_metrics(
    *,
    source: OptimizationSource,
    portfolio: PortfolioConfig,
    report: ReportConfig,
    close: pd.DataFrame,
    open_: pd.DataFrame,
    store: WideIndicatorPrecompute,
    invalid_candidate_keys: set[CandidateKey],
    extractors: Mapping[str, ExtractorSpec],
) -> Callable[..., Any]:
    """Build a split callback that slices the full-series store before simulation.

    ``close``, ``open_`` and ``store`` are closure-captured (passed through
    ``apply`` unchanged); only the per-(split,set) ``range_`` template arrives
    positionally. ``close.index`` (the full loaded-data calendar) is passed as
    the market index so the seam mask can detect gaps in purged/embargoed
    split windows. Selection and held-out sweeps use the same callback shape —
    and are handed the same ``invalid_candidate_keys`` (a required argument) —
    so they cannot drift.

    Returns a callable whose ``held_counts`` attribute is a shared
    ``multiprocessing.Manager.list`` of per-call non-executable-row counts
    accumulated during the sweep (parallel-safe via proxy serialization).
    """
    held_counts = multiprocessing.Manager().list()  # type: ignore[var-annotated]
    full_index = close.index

    def window_metrics(range_: slice, **params: Any) -> Any:
        param_names, combo_lists, n_combos, metric_keys = _extract_combos(params)
        keys = candidate_keys(combo_lists)
        invalid_positions = invalid_candidate_positions(keys, invalid_candidate_keys)
        if len(invalid_positions) == n_combos:
            return _nan_metric_frame(metric_keys, param_names, list(extractors))

        close_window = close.iloc[range_]
        open_window = open_.iloc[range_]
        indicator_window = store.window(range_, keys)
        wide_allocations = source.simulate(
            close_window, indicator_window, n_combos, **combo_lists
        )
        # Invalid Candidates are excluded by-key via classify_candidates;
        # their real simulated values (e.g. a finite cash-holding 0.0)
        # stay in the grid without masking. The all-invalid short-circuit
        # above is a pure performance guard.
        return _metrics_from_allocations(
            close_window,
            open_window,
            wide_allocations,
            portfolio,
            report,
            metric_keys,
            param_names,
            extractors,
            market_index=full_index,
            held_counts_out=held_counts,
        )

    window_metrics.held_counts = held_counts  # type: ignore[attr-defined]
    return window_metrics


def _extract_combos(
    params: Mapping[str, Any],
) -> tuple[list[str], dict[str, list[Any]], int, list[tuple]]:
    # Under mono-chunking every parameter arrives as a list of the chunk's per-combo
    # values (a single-element list for a one-combo chunk). The grouped accessor
    # returns one metric row per combo, owning the parameter MultiIndex that vbt
    # row-stacks across chunks and splits.
    param_names = list(params)
    combo_lists = {name: _combo_values(value) for name, value in params.items()}
    n_combos = len(combo_lists[param_names[0]]) if param_names else 0
    metric_keys = [
        tuple(combo_lists[name][i] for name in param_names) for i in range(n_combos)
    ]
    return param_names, combo_lists, n_combos, metric_keys


def _metrics_from_allocations(
    close_window: pd.DataFrame,
    open_window: pd.DataFrame,
    wide_allocations: Any,
    portfolio: PortfolioConfig,
    report: ReportConfig,
    metric_keys: list[tuple],
    param_names: list[str],
    extractors: Mapping[str, ExtractorSpec],
    *,
    market_index: pd.Index,
    held_counts_out: MutableSequence[int] | None = None,
) -> Any:
    if wide_allocations is vbt.NoResult:
        return vbt.NoResult
    n_symbols = len(close_window.columns)
    if n_symbols == 0 or len(wide_allocations.columns) // n_symbols < 1:
        return vbt.NoResult
    pf, held_count = simulate_portfolio_batch(
        close_window,
        wide_allocations,
        portfolio,
        open_=open_window,
        market_index=market_index,
        periods_per_year=report.periods_per_year,
    )
    if held_counts_out is not None:
        held_counts_out.append(held_count)
    return central_metrics_from_grouped_accessors(
        pf, report, metric_keys, param_names, extractors
    )


def _nan_metric_frame(
    metric_keys: list[tuple], param_names: list[str], metric_ids: list[str]
) -> pd.DataFrame:
    # float64 by construction — same grid dtype contract as
    # central_metrics_from_grouped_accessors, so vbt's row_stack concat
    # never has to reconcile divergent dtypes across windows. Columns mirror
    # the registry's extractor set so custom metrics stay aligned.
    index = pd.MultiIndex.from_tuples(metric_keys, names=param_names)
    return pd.DataFrame(np.nan, index=index, columns=metric_ids)


def _combo_values(value: Any) -> list[Any]:
    """Normalize a mono-chunk parameter into its list of per-combo values.

    Under mono-chunking vbt passes each parameter as the chunk's list of values;
    a single-combo chunk (or a ``skip_single_comb`` shortcut) arrives as a scalar.
    """
    if pd.api.types.is_list_like(value):
        return list(value)
    return [value]


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
        # the wide strategy vectorizes its candidates through numpy.
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
    source: OptimizationSource,
    portfolio: PortfolioConfig,
    report: ReportConfig,
    close: pd.DataFrame,
    open_: pd.DataFrame,
    store: WideIndicatorPrecompute,
    param_names: list[str],
    invalid_candidate_keys: set[CandidateKey],
    extractors: Mapping[str, ExtractorSpec],
    selection_held_counts: list[int] | None = None,
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
    held_out_metrics = _build_precomputed_window_metrics(
        source=source,
        portfolio=portfolio,
        report=report,
        close=close,
        open_=open_,
        store=store,
        invalid_candidate_keys=invalid_candidate_keys,
        extractors=extractors,
    )
    held_out_grid = _sweep(
        splitter=splitter,
        candidate_metrics=held_out_metrics,
        apply_input=vbt.Rep("range_"),
        params=held_out_params,
        set_=HELD_OUT_SET,
        parallel=False,
    )
    # Aggregate non-executable-row counts from both sweeps.
    held_out_held_counts: list[int] = getattr(held_out_metrics, "held_counts", [])
    non_executable_rows = sum(selection_held_counts or []) + sum(held_out_held_counts)
    return OptimizationResult(
        best=_with_held_out(result.best, held_out_grid),
        median=_with_held_out(result.median, held_out_grid),
        worst=_with_held_out(result.worst, held_out_grid),
        excluded_degenerate=result.excluded_degenerate,
        excluded_invalid=result.excluded_invalid,
        total_candidates=result.total_candidates,
        non_executable_rows=non_executable_rows,
    )


def _with_held_out(
    candidate: EvaluatedCandidate,
    held_out_grid: CandidateGrid,
) -> EvaluatedCandidate:
    key = tuple(candidate.params[name] for name in held_out_grid.param_levels)
    held_out = held_out_grid.split_metrics(key)
    return dataclasses.replace(candidate, held_out_metrics=held_out)


def _materialize_candidates(
    params: Mapping[str, vbt.Param], optimization: OptimizationConfig
) -> dict[str, list[Any]]:
    """Build the sampled candidate set once, up front, via the framework sampler.

    ``combine_params`` is the same machinery ``vbt.parameterized`` uses internally;
    materialising it here lets the precompute and the selection sweep share one
    candidate set by construction. The result maps each param name to its list of
    per-combo values (aligned across params). For a fixed seed it is deterministic.
    """
    options: dict[str, Any] = {}
    if optimization.search == "random":
        if optimization.random_subset is None:
            raise OptimizationRunnerError(
                "optimization.random_subset is required when optimization.search is 'random'"
            )
        if optimization.seed is None:
            raise OptimizationRunnerError(
                "optimization.seed is required when optimization.search is 'random' so the "
                "sampled selection grid is deterministic"
            )
        options = {"random_subset": optimization.random_subset, "seed": optimization.seed}
    return vbt.combine_params(dict(params), build_index=False, **options)


def _validate_source_param_names(params: Mapping[str, vbt.Param]) -> None:
    reserved = sorted(set(params) & OPTIMIZATION_PARAM_RESERVED_NAMES)
    if reserved:
        raise OptimizationRunnerError(
            f"optimization param names {reserved} are reserved for Aegis/VBT result "
            "coordinates; choose distinct parameter names"
        )

