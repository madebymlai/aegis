from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.configuration import OptimizationConfig
from research.aegis_research.metrics import make_default_metric_registry
from research.aegis_research.optimization.precompute import empty_precompute
from research.aegis_research.optimization.preflight import PreflightError, build_preflight
from research.aegis_research.optimization.runner import (
    OptimizationRunnerError,
    execute_optimization,
)
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.optimization.window_evaluation import ResolvedBook
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_portfolio_config,
    make_ranking_config,
    make_report_config,
    make_run_arrays,
)


def _close_frame() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=40, freq="D")
    rng = np.random.default_rng(7)
    levels = 100 + np.cumsum(rng.normal(0.0, 1.0, size=len(index)))
    return pd.DataFrame({"SYN": levels}, index=index)


def _optimization_config() -> OptimizationConfig:
    return make_optimization_config(search="grid", observation_block_bars=10)


def _preflight(
    close: pd.DataFrame,
    source: OptimizationSource,
    optimization: OptimizationConfig,
):
    return build_preflight(
        source=source,
        optimization=optimization,
        index=close.index,
        symbol_count=close.shape[1],
        metric_count=len(make_default_metric_registry().ids()),
        has_open_prices=True,
    )


def test_runner_wraps_vbt_no_results_exception_as_runner_error() -> None:
    close = _close_frame()

    def always_skip(close_window, indicator_window, n_candidates, **param_lists):
        return vbt.NoResult

    source = OptimizationSource(
        precompute=empty_precompute,
        simulate=always_skip,
        resolve_lookbacks=lambda params: {"source": 0},
        params={"fast_window": vbt.Param([2, 5])},
        output_name="active",
        evidence={"source": "always_skip"},
        diagnostics={},
        metadata={},
    )

    optimization = _optimization_config()
    with pytest.raises(OptimizationRunnerError, match="no portfolio allocations"):
        execute_optimization(
            arrays=make_run_arrays(close=close, open_=close),
            source=source,
            optimization=optimization,
            book=ResolvedBook(make_portfolio_config(fees=0, slippage=0, direction="longonly")),
            report=make_report_config(),
            ranking=make_ranking_config(metric="total_return"),
            metric_registry=make_default_metric_registry(),
            preflight=_preflight(close, source, optimization),
        )


def test_runner_pipeline_runtime_error_surfaces_to_caller() -> None:
    close = _close_frame()

    def exploding_pipeline(close_window, indicator_window, n_candidates, **param_lists):
        raise RuntimeError("pipeline blew up while running")

    source = OptimizationSource(
        precompute=empty_precompute,
        simulate=exploding_pipeline,
        resolve_lookbacks=lambda params: {"source": 0},
        params={"fast_window": vbt.Param([2, 5])},
        output_name="active",
        evidence={"source": "exploding"},
        diagnostics={},
        metadata={},
    )

    optimization = _optimization_config()
    with pytest.raises(RuntimeError, match="pipeline blew up"):
        execute_optimization(
            arrays=make_run_arrays(close=close, open_=close),
            source=source,
            optimization=optimization,
            book=ResolvedBook(make_portfolio_config(fees=0, slippage=0, direction="longonly")),
            report=make_report_config(),
            ranking=make_ranking_config(metric="total_return"),
            metric_registry=make_default_metric_registry(),
            preflight=_preflight(close, source, optimization),
        )


@pytest.mark.parametrize("reserved_name", ["split", "set", "symbol", "metric_name"])
def test_preflight_rejects_param_names_reserved_for_result_coordinates(
    reserved_name: str,
) -> None:
    close = _close_frame()

    def passthrough(close_window, indicator_window, n_candidates, **param_lists):
        return close_window

    source = OptimizationSource(
        precompute=empty_precompute,
        simulate=passthrough,
        resolve_lookbacks=lambda params: {"source": 0},
        params={reserved_name: vbt.Param([1, 2])},
        output_name="active",
        evidence={"source": "reserved_name"},
        diagnostics={},
        metadata={},
    )

    optimization = _optimization_config()
    with pytest.raises(PreflightError, match="reserved"):
        _preflight(close, source, optimization)
