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
    SAMPLED_ROWS_SOURCE_PRECOMPUTED,
    SAMPLED_ROWS_SOURCE_RESULT_GRID,
    OptimizationRunnerError,
    _extract_param_index,
    _verify_evaluated_subset,
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
    assert run.selection_grid is None
    assert run.held_out_grid is None
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
    assert run.selection_grid is not None
    assert run.held_out_grid is None, "return_grid='first' must not surface duplicated set_1 grid"
    assert "fast_window" in run.selection_grid.index.names
    assert "slow_window" in run.selection_grid.index.names
    assert METRIC_INDEX_NAME in run.selection_grid.index.names
    assert set(run.selection_grid.index.get_level_values("set")) == {"selection"}
    grid_metrics = set(run.selection_grid.index.get_level_values(METRIC_INDEX_NAME))
    assert grid_metrics == set(PORTFOLIO_METRIC_VALUE_KEYS)


def test_runner_return_grid_all_emits_distinct_selection_and_held_out_grids() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2, 5], slow=[10, 20])

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(return_grid="all"),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )

    assert run.return_grid_mode == "all"
    assert run.selection_grid is not None
    assert run.held_out_grid is not None
    selection_sets = set(run.selection_grid.index.get_level_values("set"))
    held_out_sets = set(run.held_out_grid.index.get_level_values("set"))
    assert selection_sets == {"selection"}
    assert held_out_sets == {"held_out"}
    # In return_grid="all", set_0 and set_1 grids are independent evaluations
    # over different windows, so they must not be identical row-for-row.
    selection_values = run.selection_grid.reset_index(level="set", drop=True)
    held_out_values = run.held_out_grid.reset_index(level="set", drop=True)
    assert not selection_values.equals(held_out_values), (
        "return_grid='all' must produce distinct selection and held-out grid evaluations"
    )


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
    assert len(run.sampled_index) == 3


def test_runner_sampled_index_is_deterministic_under_same_seed() -> None:
    close, open_prices = _close_open_frames()
    source_a = _build_source(fast=[2, 3, 5, 8], slow=[10, 15, 20, 30])
    source_b = _build_source(fast=[2, 3, 5, 8], slow=[10, 15, 20, 30])

    run_a = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source_a,
        optimization=_optimization_config(search="random", random_subset=5, seed=42),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )
    run_b = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source_b,
        optimization=_optimization_config(search="random", random_subset=5, seed=42),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )

    assert list(run_a.sampled_index) == list(run_b.sampled_index)


def test_runner_sampled_index_matches_grid_param_axis_for_grid_search() -> None:
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

    assert len(run.sampled_index) == 4
    sampled_pairs = set(map(tuple, run.sampled_index))
    grid_param_pairs = set(
        zip(
            run.selection_grid.index.get_level_values("fast_window"),
            run.selection_grid.index.get_level_values("slow_window"),
            strict=True,
        )
    )
    assert sampled_pairs == grid_param_pairs


def test_runner_serializes_sampled_rows_independent_of_return_grid() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2, 3, 5, 8], slow=[10, 15, 20, 30])

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(
            search="random",
            random_subset=4,
            seed=11,
            return_grid="off",
        ),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )
    payload = serialize_optimization_run(run)

    assert run.selection_grid is None
    assert run.held_out_grid is None
    assert payload["selection_grid"] is None
    assert payload["held_out_grid"] is None
    assert len(payload["sampled_rows"]["rows"]) == 4
    sampled_param_names = set(payload["sampled_rows"]["index_names"])
    assert sampled_param_names == {"fast_window", "slow_window"}


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


def test_runner_tied_param_levels_emit_paired_rows_only() -> None:
    close, open_prices = _close_open_frames()
    tied_source = OptimizationSource(
        pipeline=_ma_pipeline,
        params={
            "fast_window": vbt.Param([2, 5, 10], level=0),
            "slow_window": vbt.Param([20, 50, 100], level=0),
        },
        evidence={"source": "test"},
        diagnostics={},
        metadata={},
    )

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=tied_source,
        optimization=_optimization_config(return_grid="first"),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )

    sampled_pairs = set(map(tuple, run.sampled_index))
    assert sampled_pairs == {(2, 20), (5, 50), (10, 100)}
    grid_param_pairs = set(
        zip(
            run.selection_grid.index.get_level_values("fast_window"),
            run.selection_grid.index.get_level_values("slow_window"),
            strict=True,
        )
    )
    assert grid_param_pairs == sampled_pairs


def test_runner_conditional_params_filter_invalid_combinations() -> None:
    close, open_prices = _close_open_frames()
    cond_source = OptimizationSource(
        pipeline=_ma_pipeline,
        params={
            "fast_window": vbt.Param([2, 5, 10], condition="fast_window < slow_window"),
            "slow_window": vbt.Param([3, 8]),
        },
        evidence={"source": "test"},
        diagnostics={},
        metadata={},
    )

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=cond_source,
        optimization=_optimization_config(return_grid="first"),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )

    sampled_pairs = set(map(tuple, run.sampled_index))
    assert sampled_pairs == {(2, 3), (2, 8), (5, 8)}
    grid_param_pairs = set(
        zip(
            run.selection_grid.index.get_level_values("fast_window"),
            run.selection_grid.index.get_level_values("slow_window"),
            strict=True,
        )
    )
    assert grid_param_pairs == sampled_pairs


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


def test_serialize_optimization_run_emits_jsonable_selection_and_selection_grid() -> None:
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
    assert payload["selection_grid"] is not None
    assert payload["selection_grid"]["index_names"][:2] == ["split", "set"]
    grid_sets = {row["coordinates"]["set"] for row in payload["selection_grid"]["rows"]}
    assert grid_sets == {"selection"}
    assert payload["held_out_grid"] is None


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


def test_runner_sampled_rows_sourced_from_result_grid_when_return_grid_first() -> None:
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

    assert run.sampled_rows_source == SAMPLED_ROWS_SOURCE_RESULT_GRID, (
        "return_grid='first' has a post-execution selection_grid so evidence must "
        "come from VBT's returned index, not the pre-computed combine_params output"
    )
    evaluated_pairs = set(run.evaluated_index.to_list())
    sampled_pairs = set(run.sampled_index.to_list())
    assert evaluated_pairs <= sampled_pairs, (
        "post-execution evaluated index must be a subset of the pre-computed sampled index"
    )
    payload = serialize_optimization_run(run)
    assert payload["sampled_rows"]["source"] == SAMPLED_ROWS_SOURCE_RESULT_GRID


def test_runner_sampled_rows_falls_back_to_precomputed_when_return_grid_off() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2, 5], slow=[10, 20])

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(return_grid="off"),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    )

    assert run.sampled_rows_source == SAMPLED_ROWS_SOURCE_PRECOMPUTED, (
        "return_grid='off' has no post-execution grid so evidence falls back to "
        "the pre-computed combine_params output"
    )
    assert run.evaluated_index.equals(run.sampled_index)
    payload = serialize_optimization_run(run)
    assert payload["sampled_rows"]["source"] == SAMPLED_ROWS_SOURCE_PRECOMPUTED


def test_extract_param_index_drops_split_set_metric_levels_and_dedupes() -> None:
    index = pd.MultiIndex.from_tuples(
        [
            (0, "selection", 2, 10, "total_return"),
            (0, "selection", 2, 10, "sharpe_ratio"),
            (0, "held_out", 2, 10, "total_return"),
            (1, "selection", 5, 20, "total_return"),
        ],
        names=["split", "set", "fast_window", "slow_window", METRIC_INDEX_NAME],
    )

    projected = _extract_param_index(index)

    assert list(projected.names) == ["fast_window", "slow_window"]
    assert set(projected.to_list()) == {(2, 10), (5, 20)}


def test_verify_evaluated_subset_raises_on_drift() -> None:
    sampled = pd.MultiIndex.from_tuples(
        [(2, 10), (5, 20)], names=["fast_window", "slow_window"]
    )
    drifted = pd.MultiIndex.from_tuples(
        [(2, 10), (99, 99)], names=["fast_window", "slow_window"]
    )

    with pytest.raises(OptimizationRunnerError, match="candidate evidence drift"):
        _verify_evaluated_subset(evaluated=drifted, sampled=sampled, label="test")


def test_verify_evaluated_subset_passes_when_subset_holds() -> None:
    sampled = pd.MultiIndex.from_tuples(
        [(2, 10), (5, 20), (10, 50)], names=["fast_window", "slow_window"]
    )
    evaluated = pd.MultiIndex.from_tuples(
        [(2, 10), (5, 20)], names=["fast_window", "slow_window"]
    )

    _verify_evaluated_subset(evaluated=evaluated, sampled=sampled, label="test")
