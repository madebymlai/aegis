from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

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

OPTIMIZATION_RUN_SCHEMA_VERSION = "optimization_run.v1"
RANKING_DIRECTION_TO_SELECTION = {"desc": "max", "asc": "min"}


class OptimizationRunnerError(ValueError):
    pass


@dataclass(frozen=True)
class OptimizationRun:
    selection: pd.Series
    selection_grid: pd.Series | None
    held_out_grid: pd.Series | None
    sampled_index: pd.Index
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
    call_args: tuple[Any, ...]
    if open_prices is not None:
        call_args = (close, open_prices)
    else:
        call_args = (close,)
    output = decorated(*call_args, **dict(source.params))
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
    return OptimizationRun(
        selection=_canonicalize_role_index(selection_series),
        selection_grid=selection_grid,
        held_out_grid=held_out_grid,
        sampled_index=sampled_index,
        return_grid_mode=return_grid_mode,
        ranking_metric=ranking.metric,
        ranking_direction=ranking.direction,
        parameterized_kwargs=parameterized_kwargs,
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
            entries, exits = _coerce_pipeline_signals(pipeline(close_slice, **params))
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
        entries, exits = _coerce_pipeline_signals(pipeline(close_slice, **params))
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
        if direction == "desc":
            label = per_param.idxmax()
        else:
            label = per_param.idxmin()
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
        "sampled_rows": _serialize_param_index(run.sampled_index),
    }


def _serialize_param_index(index: pd.Index) -> dict[str, Any]:
    names = list(index.names)
    if isinstance(index, pd.MultiIndex):
        tuples = list(index)
    else:
        tuples = [(value,) for value in index]
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
