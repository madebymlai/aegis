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
    _build_selection_function,
    _extract_param_index,
    _verify_evaluated_subset,
    execute_optimization,
    serialize_optimization_run,
)
from research.aegis_research.optimization.source import OptimizationSource


def _close_open_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2024-01-01", periods=40, freq="D")
    rng = np.random.default_rng(42)
    levels_a = 100 + np.cumsum(rng.normal(0.0, 1.0, size=len(index)))
    levels_b = 100 + np.cumsum(rng.normal(0.0, 1.0, size=len(index)))
    close = pd.DataFrame({"AAA": levels_a, "BBB": levels_b}, index=index)
    open_prices = close.shift(1).bfill() + 0.1
    return close, open_prices


def _ma_pipeline(close: pd.DataFrame, fast_window: int, slow_window: int) -> pd.DataFrame:
    fast = close.rolling(fast_window, min_periods=1).mean()
    slow = close.rolling(slow_window, min_periods=1).mean()
    selected = (fast > slow).astype(object)
    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)
    active.loc[:] = selected
    return active


def _build_source(*, fast: list[int], slow: list[int]) -> OptimizationSource:
    return OptimizationSource(
        pipeline=_ma_pipeline,
        params={"fast_window": vbt.Param(fast), "slow_window": vbt.Param(slow)},
        output_name="active",
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
    mono_chunk_len=10000,
    )

    assert run.return_grid_mode == "off"
    assert run.selection_grid is None
    assert run.held_out_grid is None
    assert isinstance(run.selection, pd.DataFrame)
    assert run.selection.index.names[:2] == ["split", "set"]
    assert set(run.selection.columns) == set(PORTFOLIO_METRIC_VALUE_KEYS)
    set_values = set(run.selection.index.get_level_values("set"))
    assert set_values == {"selection", "held_out"}
    assert run.parameterized_kwargs["merge_func"] == "row_stack"
    split_count = len(set(run.selection.index.get_level_values("split")))
    assert len(run.selection) == split_count * 2


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
    mono_chunk_len=10000,
    )

    assert run.return_grid_mode == "first"
    assert run.selection_grid is not None
    assert run.held_out_grid is None, "return_grid='first' must not surface duplicated set_1 grid"
    assert isinstance(run.selection_grid, pd.DataFrame)
    assert "fast_window" in run.selection_grid.index.names
    assert "slow_window" in run.selection_grid.index.names
    assert set(run.selection_grid.columns) == set(PORTFOLIO_METRIC_VALUE_KEYS)
    assert set(run.selection_grid.index.get_level_values("set")) == {"selection"}


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
    mono_chunk_len=10000,
    )

    assert run.return_grid_mode == "all"
    assert run.selection_grid is not None
    assert run.held_out_grid is not None
    selection_sets = set(run.selection_grid.index.get_level_values("set"))
    held_out_sets = set(run.held_out_grid.index.get_level_values("set"))
    assert selection_sets == {"selection"}
    assert held_out_sets == {"held_out"}
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
    mono_chunk_len=10000,
    )

    assert run.parameterized_kwargs["random_subset"] == 3
    assert run.parameterized_kwargs["seed"] == 7
    assert run.parameterized_kwargs["merge_func"] == "row_stack"
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
    mono_chunk_len=10000,
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
    mono_chunk_len=10000,
    )

    assert list(run_a.sampled_index) == list(run_b.sampled_index)


def test_runner_requires_seed_for_random_search() -> None:
    close, open_prices = _close_open_frames()
    source = _build_source(fast=[2, 3, 5, 8], slow=[10, 15, 20, 30])

    with pytest.raises(OptimizationRunnerError, match=r"optimization\.seed"):
        execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=_optimization_config(search="random", random_subset=3),
            portfolio=PortfolioConfig(fees=0, slippage=0),
            signal=SignalConfig(),
            report=ReportConfig(),
            ranking=RankingConfig(metric="total_return", direction="desc"),
        mono_chunk_len=10000,
        )


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
    mono_chunk_len=10000,
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
    mono_chunk_len=10000,
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
    mono_chunk_len=10000,
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
    mono_chunk_len=10000,
    )

    desc_winners = (
        run_desc.selection.xs("selection", level="set")
        .sort_index(level="split")["total_return"]
        .to_numpy()
    )
    asc_winners = (
        run_asc.selection.xs("selection", level="set")
        .sort_index(level="split")["total_return"]
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
        mono_chunk_len=10000,
        )


@pytest.mark.parametrize("param_name", ["split", "set", "symbol", METRIC_INDEX_NAME])
def test_runner_rejects_reserved_param_names_in_manual_source(param_name: str) -> None:
    close, open_prices = _close_open_frames()

    def pipeline(close: pd.DataFrame, **_params: object) -> pd.DataFrame:
        return close.notna().astype(object)

    source = OptimizationSource(
        pipeline=pipeline,
        params={param_name: vbt.Param([1])},
        output_name="active",
        evidence={},
        diagnostics={},
        metadata={},
    )

    with pytest.raises(OptimizationRunnerError, match="reserved"):
        execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=_optimization_config(),
            portfolio=PortfolioConfig(),
            signal=SignalConfig(),
            report=ReportConfig(),
            ranking=RankingConfig(metric="total_return", direction="desc"),
        mono_chunk_len=10000,
        )


def test_runner_tied_param_levels_emit_paired_rows_only() -> None:
    close, open_prices = _close_open_frames()
    tied_source = OptimizationSource(
        pipeline=_ma_pipeline,
        params={
            "fast_window": vbt.Param([2, 5, 10], level=0),
            "slow_window": vbt.Param([20, 50, 100], level=0),
        },
        output_name="active",
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
    mono_chunk_len=10000,
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
        output_name="active",
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
    mono_chunk_len=10000,
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
        mono_chunk_len=10000,
        )


def test_runner_rejects_all_non_finite_ranking_metric_values() -> None:
    selection_fn = _build_selection_function(ranking_metric="total_return", direction="desc")
    grid_results = pd.DataFrame(
        {"total_return": [float("nan"), float("inf"), float("-inf")]},
        index=pd.Index([1, 2, 3], name="window"),
    )

    with pytest.raises(OptimizationRunnerError, match="non-finite"):
        selection_fn(grid_results)


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
    mono_chunk_len=10000,
    )

    payload = serialize_optimization_run(run)
    assert payload["schema_version"] == OPTIMIZATION_RUN_SCHEMA_VERSION
    assert payload["ranking_metric"] == "total_return"
    assert payload["ranking_direction"] == "desc"
    assert payload["return_grid_mode"] == "first"
    assert payload["selection"]["index_names"][:2] == ["split", "set"]
    assert set(payload["selection"]["columns"]) == set(PORTFOLIO_METRIC_VALUE_KEYS)
    first_row = payload["selection"]["rows"][0]
    assert {"selection", "held_out"} >= {first_row["coordinates"]["set"]}
    assert isinstance(first_row["metrics"]["total_return"], float)
    assert payload["selection_grid"] is not None
    assert payload["selection_grid"]["index_names"][:2] == ["split", "set"]
    grid_sets = {row["coordinates"]["set"] for row in payload["selection_grid"]["rows"]}
    assert grid_sets == {"selection"}
    assert payload["held_out_grid"] is None


def test_runner_rejects_invalid_pipeline_output_shape() -> None:
    close, open_prices = _close_open_frames()

    def bad_pipeline(close, fast_window):
        return "not a dataframe"

    source = OptimizationSource(
        pipeline=bad_pipeline,
        params={"fast_window": vbt.Param([2, 5])},
        output_name="active",
        evidence={},
        diagnostics={},
        metadata={},
    )

    with pytest.raises(OptimizationRunnerError, match=r"declared shape 'active'"):
        execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=_optimization_config(),
            portfolio=PortfolioConfig(),
            signal=SignalConfig(),
            report=ReportConfig(),
            ranking=RankingConfig(metric="total_return", direction="desc"),
        mono_chunk_len=10000,
        )


@pytest.mark.parametrize("forbidden_key", ["metrics", "portfolio", "metric_source"])
def test_runner_rejects_authoritative_fields_in_pipeline_output_mapping(forbidden_key: str) -> None:
    close, open_prices = _close_open_frames()

    def smuggling_pipeline(close, fast_window):
        return {
            "active": close.notna().astype(object),
            forbidden_key: {},
        }

    source = OptimizationSource(
        pipeline=smuggling_pipeline,
        params={"fast_window": vbt.Param([2, 5])},
        output_name="active",
        evidence={},
        diagnostics={},
        metadata={},
    )

    with pytest.raises(OptimizationRunnerError, match="authoritative"):
        execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=_optimization_config(),
            portfolio=PortfolioConfig(),
            signal=SignalConfig(),
            report=ReportConfig(),
            ranking=RankingConfig(metric="total_return", direction="desc"),
        mono_chunk_len=10000,
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
    mono_chunk_len=10000,
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
    mono_chunk_len=10000,
    )

    assert run.sampled_rows_source == SAMPLED_ROWS_SOURCE_PRECOMPUTED, (
        "return_grid='off' has no post-execution grid so evidence falls back to "
        "the pre-computed combine_params output"
    )
    assert run.evaluated_index.equals(run.sampled_index)
    payload = serialize_optimization_run(run)
    assert payload["sampled_rows"]["source"] == SAMPLED_ROWS_SOURCE_PRECOMPUTED


def test_extract_param_index_drops_split_set_levels_and_dedupes() -> None:
    index = pd.MultiIndex.from_tuples(
        [
            (0, "selection", 2, 10),
            (0, "held_out", 2, 10),
            (1, "selection", 5, 20),
            (1, "held_out", 5, 20),
        ],
        names=["split", "set", "fast_window", "slow_window"],
    )

    projected = _extract_param_index(index)

    assert list(projected.names) == ["fast_window", "slow_window"]
    assert set(projected.to_list()) == {(2, 10), (5, 20)}


def test_verify_evaluated_subset_raises_on_drift() -> None:
    sampled = pd.MultiIndex.from_tuples([(2, 10), (5, 20)], names=["fast_window", "slow_window"])
    drifted = pd.MultiIndex.from_tuples([(2, 10), (99, 99)], names=["fast_window", "slow_window"])

    with pytest.raises(OptimizationRunnerError, match="candidate evidence drift"):
        _verify_evaluated_subset(evaluated=drifted, sampled=sampled, label="test")


def test_verify_evaluated_subset_passes_when_subset_holds() -> None:
    sampled = pd.MultiIndex.from_tuples(
        [(2, 10), (5, 20), (10, 50)], names=["fast_window", "slow_window"]
    )
    evaluated = pd.MultiIndex.from_tuples([(2, 10), (5, 20)], names=["fast_window", "slow_window"])

    _verify_evaluated_subset(evaluated=evaluated, sampled=sampled, label="test")


def test_batched_path_preserves_candidate_identity_across_splits() -> None:
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
    mono_chunk_len=10000,
    )

    grid = run.selection_grid
    assert isinstance(grid, pd.DataFrame)
    param_tuples = set(
        zip(
            grid.index.get_level_values("fast_window"),
            grid.index.get_level_values("slow_window"),
            strict=True,
        )
    )
    assert param_tuples == {(2, 10), (2, 20), (5, 10), (5, 20)}
    for col in PORTFOLIO_METRIC_VALUE_KEYS:
        assert col in grid.columns


def test_batched_path_filters_noresult_candidates_without_failing() -> None:
    close, open_prices = _close_open_frames()

    def noresult_pipeline(close: pd.DataFrame, fast_window: int, slow_window: int) -> object:
        if fast_window >= slow_window:
            return vbt.NoResult
        return _ma_pipeline(close, fast_window, slow_window)

    source = OptimizationSource(
        pipeline=noresult_pipeline,
        params={"fast_window": vbt.Param([2, 15]), "slow_window": vbt.Param([10])},
        output_name="active",
        evidence={},
        diagnostics={},
        metadata={},
    )

    run = execute_optimization(
        close=close,
        open_prices=open_prices,
        source=source,
        optimization=_optimization_config(return_grid="first"),
        portfolio=PortfolioConfig(fees=0, slippage=0),
        signal=SignalConfig(),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", direction="desc"),
    mono_chunk_len=10000,
    )

    grid = run.selection_grid
    grid_params = set(
        zip(
            grid.index.get_level_values("fast_window"),
            grid.index.get_level_values("slow_window"),
            strict=True,
        )
    )
    assert (2, 10) in grid_params
    assert (15, 10) in grid_params
    noresult_rows = grid.xs(15, level="fast_window").xs(10, level="slow_window")
    assert noresult_rows["total_return"].isna().all()
    winner = run.selection.xs("selection", level="set")
    assert (winner["fast_window"] == 2).all() if "fast_window" in winner.columns else True
    winner_params = set(
        zip(winner.index.get_level_values("fast_window"),
            winner.index.get_level_values("slow_window"), strict=True)
    )
    assert all(k != (15, 10) for k in winner_params)


def test_runner_uses_mono_chunk_len_from_caller() -> None:
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
        mono_chunk_len=7,
    )

    assert run.parameterized_kwargs["mono_chunk_len"] == 7


def test_batched_path_no_scalar_simulate_portfolio_import() -> None:
    import research.aegis_research.optimization.runner as runner_mod

    assert not hasattr(runner_mod, "simulate_portfolio")
    assert not hasattr(runner_mod, "_evaluate_cv_slice")
