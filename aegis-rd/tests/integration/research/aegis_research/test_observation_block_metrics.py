from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.metrics import make_metric_registry_for
from research.aegis_research.metrics.range_extractors import FullPathPrimitives
from research.aegis_research.optimization.continuous_replay import replay_candidates
from research.aegis_research.optimization.observation_blocks import (
    ObservationBlocks,
    apply_registered_metric_to_blocks,
)
from research.aegis_research.optimization.window_evaluation import ResolvedBook
from tests.support.research.aegis_research.factories import (
    make_portfolio_config,
    make_report_config,
)


def _continuous_portfolio():
    index = pd.date_range("2024-01-01", periods=8)
    close = pd.DataFrame({"A": [10.0, 12.0, 15.0, 14.0, 12.0, 11.0, 13.0, 14.0]}, index=index)
    columns = pd.MultiIndex.from_tuples([("a", "A"), ("b", "A")], names=["candidate", "symbol"])
    allocations = pd.DataFrame(np.nan, index=index, columns=columns)
    allocations.iloc[0, :] = [1.0, 0.5]
    allocations.iloc[5, 1] = 0.0
    return replay_candidates(
        close,
        allocations,
        ResolvedBook(
            make_portfolio_config(
                direction="longonly", fees=0.001, slippage=0.0, fill_timing="next_close"
            )
        ),
        scored_start=1,
        periods_per_year=252,
    )


def _apply_total_return(
    replay: Any,
    primitives: FullPathPrimitives,
    registry: Any,
    candidate_index: pd.MultiIndex,
    bounds: list[tuple[int, int]],
) -> None:
    apply_registered_metric_to_blocks(
        ObservationBlocks.from_bounds(replay.portfolio.wrapper.index, bounds),
        replay.portfolio,
        primitives,
        registry.get("total_return"),
        registry.extractors["total_return"],
        make_report_config(),
        candidate_index,
    )


def _assert_replay_state_unchanged(
    before: tuple[pd.Series | pd.DataFrame, ...], replay: Any
) -> None:
    current_state = (
        replay.values,
        replay.positions,
        replay.cash,
        replay.orders,
        replay.trades,
    )
    for original, current in zip(before, current_state, strict=True):
        if isinstance(original, pd.Series):
            pd.testing.assert_series_equal(original, current)
        else:
            pd.testing.assert_frame_equal(original, current)


def test_native_and_custom_metrics_match_continuous_path_semantics() -> None:
    replay = _continuous_portfolio()
    portfolio = replay.portfolio
    report = make_report_config()
    registry = make_metric_registry_for(("ulcer_performance_index",))
    candidate_index = pd.MultiIndex.from_tuples([("a",), ("b",)], names=["candidate"])
    blocks = ObservationBlocks.from_bounds(portfolio.wrapper.index, [(1, 4), (4, 8)])
    primitives = FullPathPrimitives.from_portfolio(portfolio)

    matrices = {
        metric_id: apply_registered_metric_to_blocks(
            blocks,
            portfolio,
            primitives,
            registry.get(metric_id),
            registry.extractors[metric_id],
            report,
            candidate_index,
        )
        for metric_id in ("total_return", "max_dd", "sharpe_ratio", "ulcer_performance_index")
    }

    returns = primitives.canonical_returns
    expected_first_return = ((1.0 + returns.iloc[1:4].fillna(0.0)).prod() - 1.0) * 100.0
    np.testing.assert_allclose(
        matrices["total_return"].iloc[:, 0], expected_first_return, rtol=1e-12
    )
    cumulative = (1.0 + returns.fillna(0.0)).cumprod()
    expected_drawdown = (cumulative / cumulative.cummax() - 1.0).iloc[4:8].min().abs() * 100.0
    np.testing.assert_allclose(matrices["max_dd"].iloc[:, 1], expected_drawdown, rtol=1e-12)
    native_sharpe = portfolio.get_sharpe_ratio(
        sim_start=4,
        sim_end=8,
        rec_sim_range=False,
        freq=pd.Timedelta(report.freq),
        year_freq=pd.Timedelta(report.year_freq),
    )
    np.testing.assert_allclose(matrices["sharpe_ratio"].iloc[:, 1], native_sharpe, rtol=1e-12)

    block_returns = returns.iloc[4:8]
    annualized = (1.0 + block_returns.fillna(0.0)).prod() ** (
        report.periods_per_year / len(block_returns)
    ) - 1.0
    inherited_drawdown = (cumulative / cumulative.cummax() - 1.0).iloc[4:8]
    ulcer = np.sqrt((inherited_drawdown**2).mean())
    np.testing.assert_allclose(
        matrices["ulcer_performance_index"].iloc[:, 1],
        annualized / ulcer,
        rtol=1e-12,
    )


def test_moving_analysis_boundary_does_not_change_continuous_records_or_state() -> None:
    replay = _continuous_portfolio()
    before = (
        replay.values.copy(),
        replay.positions.copy(),
        replay.cash.copy(),
        replay.orders.copy(),
        replay.trades.copy(),
    )
    registry = make_metric_registry_for(())
    candidate_index = pd.MultiIndex.from_tuples([("a",), ("b",)], names=["candidate"])
    primitives = FullPathPrimitives.from_portfolio(replay.portfolio)
    _apply_total_return(replay, primitives, registry, candidate_index, [(1, 4), (4, 8)])
    _apply_total_return(replay, primitives, registry, candidate_index, [(1, 5), (5, 8)])

    _assert_replay_state_unchanged(before, replay)
