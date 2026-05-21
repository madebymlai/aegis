from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.configuration.schema import (
    OptimizationConfig,
    OptimizationEvidenceConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    RunSplitConfig,
    SignalConfig,
)
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.optimization.runner import (
    METRIC_INDEX_NAME,
    OPTIMIZATION_RUN_SCHEMA_VERSION,
    OptimizationRunnerError,
    execute_optimization,
    serialize_optimization_run,
)
from research.aegis_research.optimization.source import OptimizationSource


def _close_open_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2024-01-01", periods=40, freq="D")
    rng = np.random.default_rng(42)
    levels = 100 + np.cumsum(rng.normal(0.0, 1.0, size=len(index)))
    close = pd.DataFrame({"SYN": levels}, index=index)
    open_prices = close.shift(1).bfill() + 0.1
    return close, open_prices


def _ma_pipeline(close: pd.DataFrame, fast_window: int, slow_window: int):
    fast = close.rolling(fast_window, min_periods=1).mean()
    slow = close.rolling(slow_window, min_periods=1).mean()
    return fast > slow, fast < slow


def _build_source(*, fast: list[int], slow: list[int]) -> OptimizationSource:
    return OptimizationSource(
        pipeline=_ma_pipeline,
        params={"fast_window": vbt.Param(fast), "slow_window": vbt.Param(slow)},
        evidence={"source": "test"},
        diagnostics={},
        metadata={},
    )


def _optimization_config(
    *,
    return_grid: str = "off",
    search: str = "grid",
    random_subset: int | None = None,
    seed: int | None = None,
) -> OptimizationConfig:
    return OptimizationConfig(
        search=search,
        split=RunSplitConfig(method="from_rolling", params={"length": 20, "split": 0.5}),
        random_subset=random_subset,
        seed=seed,
        execute={},
        evidence=OptimizationEvidenceConfig(return_grid=return_grid),
    )


def test_runner_emits_selection_and_held_out_winners_per_split() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2, 5], slow=[10, 20])

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )

    assert run.return_grid_mode == "off"
    assert run.grid is None
    assert run.selection.index.names[:2] == ["split", "set"]
    assert run.selection.index.names[-1] == METRIC_INDEX_NAME
    set_values = set(run.selection.index.get_level_values("set"))
    assert set_values == {"selection", "held_out"}
    metric_values = set(run.selection.index.get_level_values(METRIC_INDEX_NAME))
    assert metric_values == set(PORTFOLIO_METRIC_VALUE_KEYS)
    assert run.parameterized_kwargs == {"merge_func": "concat"}
    split_count = len(set(run.selection.index.get_level_values("split")))
    assert len(run.selection) == split_count * 2 * len(PORTFOLIO_METRIC_VALUE_KEYS)


def test_runner_returns_grid_when_return_grid_first_is_requested() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2, 5], slow=[10, 20])

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(return_grid="first"),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )

    assert run.return_grid_mode == "first"
    assert run.grid is not None
    assert "fast_window" in run.grid.index.names
    assert "slow_window" in run.grid.index.names
    assert METRIC_INDEX_NAME in run.grid.index.names
    assert set(run.grid.index.get_level_values("set")) == {"selection", "held_out"}
    grid_metrics = set(run.grid.index.get_level_values(METRIC_INDEX_NAME))
    assert grid_metrics == set(PORTFOLIO_METRIC_VALUE_KEYS)


def test_runner_threads_random_subset_and_seed_into_parameterized_kwargs() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2, 3, 5, 8], slow=[10, 15, 20, 30])

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(search="random", random_subset=3, seed=7),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )

    assert run.parameterized_kwargs["random_subset"] == 3
    assert run.parameterized_kwargs["seed"] == 7


def test_runner_selection_projects_on_ranking_metric_across_central_catalog() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2, 5], slow=[10, 20])

    run_desc = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )
    run_asc = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="asc"),
    )

    desc_winners = (
        run_desc.selection.xs("total_return", level=METRIC_INDEX_NAME)
        .xs("selection", level="set")
        .sort_index(level="split")
        .to_numpy()
    )
    asc_winners = (
        run_asc.selection.xs("total_return", level=METRIC_INDEX_NAME)
        .xs("selection", level="set")
        .sort_index(level="split")
        .to_numpy()
    )
    assert (desc_winners >= asc_winners).all()


def test_runner_rejects_ranking_metric_outside_central_catalog() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2], slow=[10])

    with pytest.raises(OptimizationRunnerError, match="central portfolio metric catalog"):
        execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=_optimization_config(),
            portfolio=PortfolioConfig(fees=0, slippage=0),
            signal=SignalConfig(),
            report=ReportConfig(),
            ranking=RankingConfig(metric="not_a_real_metric", direction="desc"),
        )


def test_runner_rejects_unsupported_ranking_direction() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2], slow=[10])

    with pytest.raises(OptimizationRunnerError, match="ranking direction"):
        execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=_optimization_config(),
            portfolio=PortfolioConfig(),
            signal=SignalConfig(),
            report=ReportConfig(),
            ranking=RankingConfig(metric="total_return", direction="sideways"),
        )


def test_serialize_optimization_run_emits_jsonable_selection_and_grid_rows() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2, 5], slow=[10, 20])

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(return_grid="first"),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )

    payload = serialize_optimization_run(run)
    assert payload["schema_version"] == OPTIMIZATION_RUN_SCHEMA_VERSION
    assert payload["ranking_metric"] == "total_return"
    assert payload["ranking_direction"] == "desc"
    assert payload["return_grid_mode"] == "first"
    assert payload["selection"]["index_names"][:2] == ["split", "set"]
    first_row = payload["selection"]["rows"][0]
    assert {"selection", "held_out"} >= {first_row["coordinates"]["set"]}
    assert isinstance(first_row["value"], float)
    assert payload["grid"] is not None
    assert payload["grid"]["index_names"][:2] == ["split", "set"]


def test_runner_rejects_invalid_pipeline_signal_shape() -> None:
    close, open_prices = _close_open_frames()

    def bad_pipeline(close, fast_window):
        return "not a tuple"

    source = OptimizationSource(
        pipeline=bad_pipeline,
        params={"fast_window": vbt.Param([2, 5])},
        evidence={},
        diagnostics={},
        metadata={},
    )

    with pytest.raises(OptimizationRunnerError, match="entries.*exits"):
        execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=_optimization_config(),
            portfolio=PortfolioConfig(),
            signal=SignalConfig(),
            report=ReportConfig(),
            ranking=RankingConfig(metric="total_return", direction="desc"),
        )
