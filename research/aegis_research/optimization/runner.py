from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.portfolios import simulate_portfolio
from research.aegis_research.reports import portfolio_metrics

METRIC_INDEX_NAME = "metric_name"
NON_PARAM_LEVEL_NAMES = frozenset({"split", "set", "symbol", METRIC_INDEX_NAME})

OPTIMIZATION_RUN_SCHEMA_VERSION = "optimization_run.v1"
RANKING_DIRECTION_TO_SELECTION = {"desc": "max", "asc": "min"}

SAMPLED_ROWS_SOURCE_RESULT_GRID = "result_grid"
SAMPLED_ROWS_SOURCE_PRECOMPUTED = "combine_params_precomputed"


class OptimizationRunnerError(ValueError):
    pass


@dataclass(frozen=True)
class OptimizationRun:
    selection: pd.Series
    selection_grid: pd.Series | None
    held_out_grid: pd.Series | None
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
    sampled_index = _build_sampled_index(source.params, optimization)
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
        merge_func="concat",
        selection=vbt.RepFunc(selection_fn),
        return_grid=return_grid_kw,
    )
    call_args: tuple[Any, ...] = (
        (close, open_prices) if open_prices is not None else (close,)
    )
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
        selection_series = output
        selection_grid: pd.Series | None = None
        held_out_grid: pd.Series | None = None
    else:
        raw_grid, selection_series = output
        canon_grid = _canonicalize_role_index(raw_grid)
        selection_grid = canon_grid.xs("selection", level="set", drop_level=False)
        if return_grid_mode == "all":
            held_out_grid = canon_grid.xs("held_out", level="set", drop_level=False)
        else:
            held_out_grid = None
    canonical_selection = _canonicalize_role_index(selection_series)
    winner_param_index = _extract_param_index(canonical_selection.index)
    _verify_evaluated_subset(
        evaluated=winner_param_index,
        sampled=sampled_index,
        label="selection winners",
    )
    if selection_grid is not None:
        evaluated_index = _extract_param_index(selection_grid.index)
        _verify_evaluated_subset(
            evaluated=evaluated_index,
            sampled=sampled_index,
            label="selection grid",
        )
        sampled_rows_source = SAMPLED_ROWS_SOURCE_RESULT_GRID
    else:
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
    projection = index.droplevel(
        [name for name in index.names if name not in param_levels]
    )
    if isinstance(projection, pd.MultiIndex):
        return projection.unique()
    return pd.Index(projection.unique(), name=param_levels[0])


def _verify_evaluated_subset(
    *,
    evaluated: pd.Index,
    sampled: pd.Index,
    label: str,
) -> None:
    evaluated_set = set(evaluated.to_list() if isinstance(evaluated, pd.MultiIndex) else evaluated.tolist())
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

    if has_open_prices:

        def cv_callable(close_slice, open_slice, **params):
            pipeline_output = pipeline(close_slice, **params)
            if pipeline_output is vbt.NoResult:
                return vbt.NoResult
            entries, exits = _coerce_pipeline_signals(pipeline_output)
            result = simulate_portfolio(
                close_slice,
                entries,
                exits,
                portfolio,
                signal,
                open_prices=open_slice,
                market_index=market_index,
            )
            return _central_metric_series(result.portfolio, report)

        return cv_callable, ["close_slice", "open_slice"]

    def cv_callable_no_open(close_slice, **params):
        pipeline_output = pipeline(close_slice, **params)
        if pipeline_output is vbt.NoResult:
            return vbt.NoResult
        entries, exits = _coerce_pipeline_signals(pipeline_output)
        result = simulate_portfolio(
            close_slice,
            entries,
            exits,
            portfolio,
            signal,
            open_prices=None,
            market_index=market_index,
        )
        return _central_metric_series(result.portfolio, report)

    return cv_callable_no_open, ["close_slice"]


def _coerce_pipeline_signals(value: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    if isinstance(value, tuple) and len(value) == 2:
        entries, exits = value
    elif isinstance(value, Mapping) and "entries" in value and "exits" in value:
        entries = value["entries"]
        exits = value["exits"]
    else:
        raise OptimizationRunnerError(
            "optimization pipeline must return either an (entries, exits) tuple "
            "or a mapping with 'entries' and 'exits' frames"
        )
    if not isinstance(entries, pd.DataFrame) or not isinstance(exits, pd.DataFrame):
        raise OptimizationRunnerError(
            "optimization pipeline must return entries and exits as pandas DataFrames"
        )
    return entries, exits


def _central_metric_series(portfolio: Any, report: ReportConfig) -> pd.Series:
    metrics = portfolio_metrics(portfolio, report)
    missing = [name for name in PORTFOLIO_METRIC_VALUE_KEYS if name not in metrics]
    if missing:
        raise OptimizationRunnerError(
            f"central portfolio metrics missing keys {sorted(missing)}; "
            f"got {sorted(set(metrics) & set(PORTFOLIO_METRIC_VALUE_KEYS))}"
        )
    series = pd.Series(
        {name: metrics[name] for name in PORTFOLIO_METRIC_VALUE_KEYS},
        name="value",
    )
    series.index.name = METRIC_INDEX_NAME
    return series


def _build_selection_function(*, ranking_metric: str, direction: str):
    def selection(grid_results: pd.Series) -> Any:
        per_param = grid_results.xs(ranking_metric, level=METRIC_INDEX_NAME)
        if not isinstance(per_param, pd.Series):
            per_param = pd.Series(per_param)
        per_param = per_param.astype(float)
        finite = per_param.dropna()
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
    parameterized_kwargs: dict[str, Any] = {"merge_func": "concat"}
    if optimization.search == "random":
        if optimization.random_subset is None:
            raise OptimizationRunnerError(
                "optimization.random_subset is required when optimization.search is 'random'"
            )
        parameterized_kwargs["random_subset"] = optimization.random_subset
    if optimization.seed is not None:
        parameterized_kwargs["seed"] = optimization.seed
    parameterized_kwargs.update(dict(optimization.execute))
    return parameterized_kwargs


def _canonicalize_role_index(series: pd.Series) -> pd.Series:
    if not isinstance(series.index, pd.MultiIndex):
        return series
    if "set" not in series.index.names:
        return series
    set_position = series.index.names.index("set")
    level_arrays = [series.index.get_level_values(i) for i in range(series.index.nlevels)]
    level_arrays[set_position] = pd.Index(
        [_role_for_set_label(value) for value in level_arrays[set_position]],
        name="set",
    )
    canonical = series.copy()
    canonical.index = pd.MultiIndex.from_arrays(level_arrays, names=series.index.names)
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
        "selection": _serialize_param_series(run.selection),
        "selection_grid": (
            _serialize_param_series(run.selection_grid)
            if run.selection_grid is not None
            else None
        ),
        "held_out_grid": (
            _serialize_param_series(run.held_out_grid)
            if run.held_out_grid is not None
            else None
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


def _serialize_param_series(series: pd.Series) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    names = list(series.index.names)
    if isinstance(series.index, pd.MultiIndex):
        tuples = list(series.index)
    else:
        tuples = [(value,) for value in series.index]
    for value, key in zip(series.to_numpy(), tuples, strict=True):
        rows.append(
            {
                "coordinates": {
                    name: _scalar(component)
                    for name, component in zip(names, key, strict=True)
                },
                "value": _scalar(value),
            }
        )
    return {"index_names": names, "rows": rows}


def _scalar_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _scalar(item) for key, item in value.items()}


def _scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return value
    return value
