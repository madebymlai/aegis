"""Optimization runner.

Wraps an :class:`OptimizationSource` pipeline in ``vbt.cv_split`` for native
parameter optimization and emits the canonical evidence shape (selection
winners, optional grid, post-execution sampled rows, parameterized kwargs).

VBT execution-policy layering
-----------------------------

``optimization.execute`` in the run config flows into ``parameterized_kwargs``
of ``vbt.cv_split`` -- the **inner** per-(split, set) parameter execution
layer. It controls how the param grid is executed within a single
(split, set), e.g. ``mono_chunk_meta``, ``n_chunks``, ``chunk_len``,
``show_progress``, and ``jitted``. Aegis reserves keys that own search,
evidence, ranking, and merge semantics (see
``OPTIMIZATION_EXECUTE_RESERVED_KEYS`` in ``configuration/validation.py``).

The **outer** split-execution layer (cv_split's ``execute_kwargs``) is **not**
exposed by this runner. VBT requires that "train and test sets within each
split must execute in the same thread/process due to the way grid results are
stored and accessed using grid_results_map." Defaulting outer execution to
sequential keeps that invariant safe; any future opt-in for parallel split
execution must preserve set co-residency per split.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from vectorbtpro import vbt
from vectorbtpro.utils.execution import NoResultsException

from research.aegis_research.configuration.schema import (
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    SignalConfig,
)
from research.aegis_research.metrics.accessors import central_metrics_from_grouped_accessors
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.optimization.source import (
    OPTIMIZATION_PARAM_RESERVED_NAMES,
    OPTIMIZATION_SOURCE_FORBIDDEN_KEYS,
    OptimizationSource,
)
from research.aegis_research.portfolio_policy import convert_to_allocations
from research.aegis_research.portfolios import SYMBOL_LEVEL, simulate_portfolio_batch

METRIC_INDEX_NAME = "metric_name"
NON_PARAM_LEVEL_NAMES = OPTIMIZATION_PARAM_RESERVED_NAMES
PIPELINE_OUTPUT_FORBIDDEN_KEYS = OPTIMIZATION_SOURCE_FORBIDDEN_KEYS

OPTIMIZATION_RUN_SCHEMA_VERSION = "optimization_run.v1"
RANKING_DIRECTION_TO_SELECTION = {"desc": "max", "asc": "min"}

SAMPLED_ROWS_SOURCE_RESULT_GRID = "result_grid"
SAMPLED_ROWS_SOURCE_PRECOMPUTED = "combine_params_precomputed"


class OptimizationRunnerError(ValueError):
    pass


@dataclass(frozen=True)
class OptimizationRun:
    selection: pd.DataFrame
    selection_grid: pd.DataFrame | None
    held_out_grid: pd.DataFrame | None
    sampled_index: pd.Index
    evaluated_index: pd.Index
    sampled_rows_source: str
    return_grid_mode: str
    ranking_metric: str
    ranking_direction: str
    parameterized_kwargs: dict[str, Any]


def execute_optimization(
    *,
    close: pd.DataFrame,
    open_prices: pd.DataFrame | None,
    source: OptimizationSource,
    optimization: OptimizationConfig,
    portfolio: PortfolioConfig,
    signal: SignalConfig,
    report: ReportConfig,
    ranking: RankingConfig,
) -> OptimizationRun:
    if ranking.direction not in RANKING_DIRECTION_TO_SELECTION:
        raise OptimizationRunnerError(
            f"optimization ranking direction must be one of "
            f"{sorted(RANKING_DIRECTION_TO_SELECTION)}; got {ranking.direction!r}"
        )
    _validate_source_param_names(source.params)
    cv_callable, takeable_args = _build_cv_callable(
        source=source,
        portfolio=portfolio,
        signal=signal,
        report=report,
        ranking_metric=ranking.metric,
        market_index=close.index,
        has_open_prices=open_prices is not None,
    )
    parameterized_kwargs = _build_parameterized_kwargs(optimization)
    return_grid_mode = optimization.evidence.return_grid
    return_grid_kw: str | None = return_grid_mode if return_grid_mode != "off" else None
    selection_fn = _build_selection_function(
        ranking_metric=ranking.metric,
        direction=ranking.direction,
    )
    decorated = vbt.cv_split(
        cv_callable,
        splitter=optimization.split.method,
        splitter_kwargs=dict(optimization.split.params),
        takeable_args=takeable_args,
        parameterized_kwargs=parameterized_kwargs,
        merge_func="row_stack",
        selection=vbt.RepFunc(selection_fn),
        return_grid=return_grid_kw,
    )
    call_args: tuple[Any, ...] = (close, open_prices) if open_prices is not None else (close,)
    try:
        output = decorated(*call_args, **dict(source.params))
    except NoResultsException as error:
        raise OptimizationRunnerError(
            "optimization pipeline produced no usable results across the requested "
            "parameter grid; every sampled combination returned vbt.NoResult or was "
            "filtered out — return NaN metrics from invalid combinations instead so "
            "they remain visible in evidence"
        ) from error
    if return_grid_kw is None:
        selection_df = output
        selection_grid: pd.DataFrame | None = None
        held_out_grid: pd.DataFrame | None = None
    else:
        raw_grid, selection_df = output
        canon_grid = _canonicalize_role_index(raw_grid)
        selection_grid = canon_grid.xs("selection", level="set", drop_level=False)
        if return_grid_mode == "all":
            held_out_grid = canon_grid.xs("held_out", level="set", drop_level=False)
        else:
            held_out_grid = None
    canonical_selection = _canonicalize_role_index(selection_df)
    winner_param_index = _extract_param_index(canonical_selection.index)
    if selection_grid is not None:
        sampled_index = _extract_param_index(selection_grid.index)
        _verify_evaluated_subset(
            evaluated=winner_param_index,
            sampled=sampled_index,
            label="selection winners",
        )
        evaluated_index = sampled_index
        sampled_rows_source = SAMPLED_ROWS_SOURCE_RESULT_GRID
    else:
        sampled_index = _build_sampled_index(source.params, optimization)
        _verify_evaluated_subset(
            evaluated=winner_param_index,
            sampled=sampled_index,
            label="selection winners",
        )
        evaluated_index = sampled_index
        sampled_rows_source = SAMPLED_ROWS_SOURCE_PRECOMPUTED
    return OptimizationRun(
        selection=canonical_selection,
        selection_grid=selection_grid,
        held_out_grid=held_out_grid,
        sampled_index=sampled_index,
        evaluated_index=evaluated_index,
        sampled_rows_source=sampled_rows_source,
        return_grid_mode=return_grid_mode,
        ranking_metric=ranking.metric,
        ranking_direction=ranking.direction,
        parameterized_kwargs=parameterized_kwargs,
    )


def _extract_param_index(index: pd.Index) -> pd.Index:
    if not isinstance(index, pd.MultiIndex):
        raise OptimizationRunnerError(
            "cannot extract VBT param coordinates from a non-MultiIndex result"
        )
    param_levels = [name for name in index.names if name not in NON_PARAM_LEVEL_NAMES]
    if not param_levels:
        raise OptimizationRunnerError(
            f"VBT result index carries no param levels; got {list(index.names)}"
        )
    projection = index.droplevel([name for name in index.names if name not in param_levels])
    if isinstance(projection, pd.MultiIndex):
        return projection.unique()
    return pd.Index(projection.unique(), name=param_levels[0])


def _validate_source_param_names(params: Mapping[str, vbt.Param]) -> None:
    reserved = sorted(set(params) & OPTIMIZATION_PARAM_RESERVED_NAMES)
    if reserved:
        raise OptimizationRunnerError(
            f"optimization param names {reserved} are reserved for Aegis/VBT result "
            "coordinates; choose distinct parameter names"
        )


def _verify_evaluated_subset(
    *,
    evaluated: pd.Index,
    sampled: pd.Index,
    label: str,
) -> None:
    evaluated_set = set(
        evaluated.to_list() if isinstance(evaluated, pd.MultiIndex) else evaluated.tolist()
    )
    sampled_set = set(sampled.to_list() if isinstance(sampled, pd.MultiIndex) else sampled.tolist())
    missing = evaluated_set - sampled_set
    if missing:
        examples = sorted(repr(item) for item in list(missing)[:5])
        raise OptimizationRunnerError(
            f"optimization candidate evidence drift: {label} contains parameter rows "
            f"not present in the pre-computed sampled set; execution evaluated "
            f"combinations that combine_params did not enumerate. Examples: {examples}. "
            "This indicates a divergence between the pre-execution sampling path "
            "(used for preflight + evidence) and the actual execution sampling. "
            "Fix the runner's sampled_index derivation."
        )


def _build_sampled_index(
    params: Mapping[str, vbt.Param],
    optimization: OptimizationConfig,
) -> pd.Index:
    combine_kwargs: dict[str, Any] = {"build_index": True}
    if optimization.search == "random":
        combine_kwargs["random_subset"] = optimization.random_subset
        combine_kwargs["seed"] = optimization.seed
        combine_kwargs["random_sort"] = True
    _, index = vbt.combine_params(dict(params), **combine_kwargs)
    return index


def _build_cv_callable(
    *,
    source: OptimizationSource,
    portfolio: PortfolioConfig,
    signal: SignalConfig,
    report: ReportConfig,
    ranking_metric: str,
    market_index: pd.Index,
    has_open_prices: bool,
) -> tuple[Any, list[str]]:
    pipeline = source.pipeline
    if ranking_metric not in PORTFOLIO_METRIC_VALUE_KEYS:
        raise OptimizationRunnerError(
            f"optimization ranking metric {ranking_metric!r} is not in the central "
            f"portfolio metric catalog: {sorted(PORTFOLIO_METRIC_VALUE_KEYS)}"
        )

    declared_shape = source.output_name
    target_exposure_cap = portfolio.target_exposure_cap
    param_names = sorted(source.params)

    def _evaluate_batch(close_slice: pd.DataFrame, **params: Any) -> Any:
        combo_lists = {name: (vals if isinstance(vals, list) else [vals]) for name, vals in params.items()}
        n_combos = len(next(iter(combo_lists.values())))
        combos = [
            {name: combo_lists[name][i] for name in param_names}
            for i in range(n_combos)
        ]
        all_keys = [tuple(combo[name] for name in param_names) for combo in combos]
        alloc_frames: list[pd.DataFrame] = []
        valid_keys: list[tuple] = []
        valid_positions: list[int] = []
        for i, combo in enumerate(combos):
            pipeline_output = pipeline(close_slice, **combo)
            if pipeline_output is vbt.NoResult:
                continue
            raw_output = _coerce_pipeline_output(pipeline_output, declared_shape)
            allocations = convert_to_allocations(
                raw_output,
                declared_shape,
                close_columns=close_slice.columns,
                target_exposure_cap=target_exposure_cap,
                direction=portfolio.direction,
            )
            alloc_frames.append(allocations)
            valid_keys.append(all_keys[i])
            valid_positions.append(i)
        if not alloc_frames:
            return vbt.NoResult
        wide = _column_stack_allocations(alloc_frames, valid_keys, param_names, close_slice.columns)
        result = simulate_portfolio_batch(close_slice, wide, portfolio, market_index=market_index)
        valid_metrics = central_metrics_from_grouped_accessors(
            result.portfolio, report, valid_keys, param_names,
        )
        full_index = pd.MultiIndex.from_tuples(all_keys, names=param_names)
        full_df = pd.DataFrame(np.nan, index=full_index, columns=valid_metrics.columns)
        full_df.iloc[valid_positions] = valid_metrics.values
        return full_df

    if has_open_prices:

        def cv_callable(close_slice, open_slice, **params):
            return _evaluate_batch(close_slice, **params)

        return cv_callable, ["close_slice", "open_slice"]

    def cv_callable_no_open(close_slice, **params):
        return _evaluate_batch(close_slice, **params)

    return cv_callable_no_open, ["close_slice"]


def _coerce_pipeline_output(value: Any, declared_shape: str) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        frame = value
    elif isinstance(value, Mapping):
        forbidden = sorted(set(value) & PIPELINE_OUTPUT_FORBIDDEN_KEYS)
        if forbidden:
            raise OptimizationRunnerError(
                "optimization pipeline output mappings must not return authoritative metrics, "
                f"portfolio fields, or candidate-axis fields: {forbidden}"
            )
        emitted = {key for key in value if isinstance(value[key], pd.DataFrame)}
        if declared_shape not in value:
            raise OptimizationRunnerError(
                f"component declared {declared_shape!r} but pipeline did not emit {declared_shape!r}; "
                f"emitted shapes: {sorted(emitted)}"
            )
        other_shapes = sorted(emitted - {declared_shape})
        if other_shapes:
            raise OptimizationRunnerError(
                f"optimization pipeline emitted {other_shapes} alongside declared shape "
                f"{declared_shape!r}; pipeline must emit exactly the declared shape"
            )
        frame = value[declared_shape]
    else:
        raise OptimizationRunnerError(
            f"optimization pipeline must return a pandas DataFrame for declared shape "
            f"{declared_shape!r} or a mapping containing it; got {type(value).__name__}"
        )
    if not isinstance(frame, pd.DataFrame):
        raise OptimizationRunnerError(
            f"optimization pipeline must return declared shape {declared_shape!r} "
            "as a pandas DataFrame"
        )
    return frame



def _column_stack_allocations(
    alloc_frames: list[pd.DataFrame],
    candidate_keys: list[tuple],
    param_names: list[str],
    symbol_columns: pd.Index,
) -> pd.DataFrame:
    all_columns: list[tuple] = []
    all_data: dict[tuple, pd.Series] = {}
    for key, alloc in zip(candidate_keys, alloc_frames, strict=True):
        for symbol in symbol_columns:
            col = (*key, symbol) if len(param_names) > 1 else (key[0], symbol)
            all_columns.append(col)
            all_data[col] = alloc[symbol]
    mi = pd.MultiIndex.from_tuples(all_columns, names=param_names + [SYMBOL_LEVEL])
    wide = pd.DataFrame(all_data, index=alloc_frames[0].index)
    wide.columns = mi
    return wide


def _build_selection_function(*, ranking_metric: str, direction: str):
    def selection(grid_results: pd.DataFrame) -> Any:
        per_param = grid_results[ranking_metric].astype(float)
        finite = per_param[np.isfinite(per_param.to_numpy())]
        if finite.empty:
            raise OptimizationRunnerError(
                f"optimization selection cannot rank by {ranking_metric!r}: every "
                "sampled parameter row returned a non-finite value (NaN/inf). Inspect "
                "pipeline diagnostics for the failing combinations"
            )
        label = finite.idxmax() if direction == "desc" else finite.idxmin()
        return vbt.LabelSel([label])

    return selection


def _build_parameterized_kwargs(optimization: OptimizationConfig) -> dict[str, Any]:
    parameterized_kwargs: dict[str, Any] = {"merge_func": "row_stack", "mono_chunk_len": 10000}
    if optimization.search == "random":
        if optimization.random_subset is None:
            raise OptimizationRunnerError(
                "optimization.random_subset is required when optimization.search is 'random'"
            )
        if optimization.seed is None:
            raise OptimizationRunnerError(
                "optimization.seed is required when optimization.search is 'random' so "
                "precomputed sampled evidence matches VBT execution"
            )
        parameterized_kwargs["random_subset"] = optimization.random_subset
    if optimization.seed is not None:
        parameterized_kwargs["seed"] = optimization.seed
    parameterized_kwargs.update(dict(optimization.execute))
    return parameterized_kwargs


def _canonicalize_role_index(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.MultiIndex):
        return frame
    if "set" not in frame.index.names:
        return frame
    set_position = frame.index.names.index("set")
    level_arrays = [frame.index.get_level_values(i) for i in range(frame.index.nlevels)]
    level_arrays[set_position] = pd.Index(
        [_role_for_set_label(value) for value in level_arrays[set_position]],
        name="set",
    )
    canonical = frame.copy()
    canonical.index = pd.MultiIndex.from_arrays(level_arrays, names=frame.index.names)
    return canonical


def _role_for_set_label(label: Any) -> str:
    text = str(label)
    if text in {"set_0", "train", "selection"}:
        return "selection"
    if text in {"set_1", "test", "held_out"}:
        return "held_out"
    raise OptimizationRunnerError(
        f"optimization received unexpected VBT set label {label!r}; "
        "expected positional pair (set_0/set_1, train/test, or selection/held_out)"
    )


def serialize_optimization_run(run: OptimizationRun) -> dict[str, Any]:
    sampled_rows_payload = _serialize_param_index(run.evaluated_index)
    sampled_rows_payload["source"] = run.sampled_rows_source
    return {
        "schema_version": OPTIMIZATION_RUN_SCHEMA_VERSION,
        "ranking_metric": run.ranking_metric,
        "ranking_direction": run.ranking_direction,
        "return_grid_mode": run.return_grid_mode,
        "parameterized_kwargs": _scalar_mapping(run.parameterized_kwargs),
        "selection": _serialize_param_dataframe(run.selection),
        "selection_grid": (
            _serialize_param_dataframe(run.selection_grid) if run.selection_grid is not None else None
        ),
        "held_out_grid": (
            _serialize_param_dataframe(run.held_out_grid) if run.held_out_grid is not None else None
        ),
        "sampled_rows": sampled_rows_payload,
    }


def _serialize_param_index(index: pd.Index) -> dict[str, Any]:
    names = list(index.names)
    tuples = list(index) if isinstance(index, pd.MultiIndex) else [(value,) for value in index]
    rows = [
        {name: _scalar(component) for name, component in zip(names, key, strict=True)}
        for key in tuples
    ]
    return {"index_names": names, "rows": rows}


def _serialize_param_dataframe(frame: pd.DataFrame) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    names = list(frame.index.names)
    if isinstance(frame.index, pd.MultiIndex):
        tuples = list(frame.index)
    else:
        tuples = [(value,) for value in frame.index]
    for key, (_, row) in zip(tuples, frame.iterrows(), strict=True):
        rows.append(
            {
                "coordinates": {
                    name: _scalar(component) for name, component in zip(names, key, strict=True)
                },
                "metrics": {col: _scalar(row[col]) for col in frame.columns},
            }
        )
    return {"index_names": names, "columns": list(frame.columns), "rows": rows}


def _scalar_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _scalar(item) for key, item in value.items()}


def _scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return value
    return value
