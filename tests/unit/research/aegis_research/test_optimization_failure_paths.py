from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.configuration import OptimizationConfig
from research.aegis_research.metrics import make_default_metric_registry
from research.aegis_research.optimization.precompute import empty_precompute
from research.aegis_research.optimization.runner import (
    OptimizationRunnerError,
    execute_optimization,
)
from research.aegis_research.optimization.source import OptimizationSource
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_portfolio_config,
    make_ranking_config,
    make_report_config,
    make_run_split_config,
)


def _close_frame() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=40, freq="D")
    rng = np.random.default_rng(7)
    levels = 100 + np.cumsum(rng.normal(0.0, 1.0, size=len(index)))
    return pd.DataFrame({"SYN": levels}, index=index)


def _optimization_config() -> OptimizationConfig:
    return make_optimization_config(
        search="grid",
        split=make_run_split_config(method="from_rolling", params={"length": 20, "split": 0.5}),
    )


def test_runner_wraps_vbt_no_results_exception_as_runner_error() -> None:
    close = _close_frame()

    def always_skip(close_window, indicator_window, n_candidates, **param_lists):
        return vbt.NoResult

    source = OptimizationSource(
        precompute=empty_precompute,
        simulate=always_skip,
        params={"fast_window": vbt.Param([2, 5])},
        output_name="active",
        evidence={"source": "always_skip"},
        diagnostics={},
        metadata={},
    )

    with pytest.raises(OptimizationRunnerError, match="no usable results"):
        execute_optimization(
            close=close,
            open_=close,
            source=source,
            optimization=_optimization_config(),
            portfolio=make_portfolio_config(fees=0, slippage=0, direction="longonly"),
            report=make_report_config(),
            ranking=make_ranking_config(metric="total_return"),
            metric_registry=make_default_metric_registry(),
        )


def test_runner_pipeline_runtime_error_surfaces_to_caller() -> None:
    close = _close_frame()

    def exploding_pipeline(close_window, indicator_window, n_candidates, **param_lists):
        raise RuntimeError("pipeline blew up while running")

    source = OptimizationSource(
        precompute=empty_precompute,
        simulate=exploding_pipeline,
        params={"fast_window": vbt.Param([2, 5])},
        output_name="active",
        evidence={"source": "exploding"},
        diagnostics={},
        metadata={},
    )

    with pytest.raises(RuntimeError, match="pipeline blew up"):
        execute_optimization(
            close=close,
            open_=close,
            source=source,
            optimization=_optimization_config(),
            portfolio=make_portfolio_config(fees=0, slippage=0, direction="longonly"),
            report=make_report_config(),
            ranking=make_ranking_config(metric="total_return"),
            metric_registry=make_default_metric_registry(),
        )
