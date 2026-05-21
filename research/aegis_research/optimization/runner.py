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
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.portfolios import simulate_portfolio
from research.aegis_research.reports import portfolio_metrics

OPTIMIZATION_RUN_SCHEMA_VERSION = "optimization_run.v1"
RANKING_DIRECTION_TO_SELECTION = {"desc": "max", "asc": "min"}


class OptimizationRunnerError(ValueError):
    pass


@dataclass(frozen=True)
class OptimizationRun:
    selection: pd.Series
    grid: pd.Series | None
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
    return_grid_mode = optimization.evidence.return_grid
    return_grid_kw: str | None = return_grid_mode if return_grid_mode != "off" else None
    decorated = vbt.cv_split(
        cv_callable,
        splitter=optimization.split.method,
        splitter_kwargs=dict(optimization.split.params),
        takeable_args=takeable_args,
        parameterized_kwargs=parameterized_kwargs,
        merge_func="concat",
        selection=RANKING_DIRECTION_TO_SELECTION[ranking.direction],
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
        grid_series: pd.Series | None = None
    else:
        grid_series, selection_series = output
    return OptimizationRun(
        selection=_canonicalize_role_index(selection_series),
        grid=_canonicalize_role_index(grid_series) if grid_series is not None else None,
        return_grid_mode=return_grid_mode,
        ranking_metric=ranking.metric,
        ranking_direction=ranking.direction,
        parameterized_kwargs=parameterized_kwargs,
    )


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
            return _select_ranking_metric(result.portfolio, report, ranking_metric)

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
        return _select_ranking_metric(result.portfolio, report, ranking_metric)

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


def _select_ranking_metric(portfolio: Any, report: ReportConfig, ranking_metric: str) -> Any:
    metrics = portfolio_metrics(portfolio, report)
    if ranking_metric not in metrics:
        raise OptimizationRunnerError(
            f"optimization ranking metric {ranking_metric!r} missing from portfolio metrics"
        )
    return metrics[ranking_metric]


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
        "grid": _serialize_param_series(run.grid) if run.grid is not None else None,
    }


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
