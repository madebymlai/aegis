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
from research.aegis_research.portfolio_simulation import ResolvedBook
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


def test_native_and_custom_metrics_match_continuous_path_semantics() -> None:
    replay = _continuous_portfolio()
    portfolio = replay.portfolio
    report = make_report_config()
    registry = make_metric_registry_for(("ulcer_performance_index",))
    candidate_index = pd.MultiIndex.from_tuples([("a",), ("b",)], names=["candidate"])
    blocks = ObservationBlocks.from_bounds(portfolio.wrapper.index, [(1, 4), (4, 8)])
    primitives = FullPathPrimitives.from_portfolio(portfolio)

    total_return = apply_registered_metric_to_blocks(
        blocks,
        portfolio,
        primitives,
        registry.get("total_return"),
        registry.extractors["total_return"],
        report,
        candidate_index,
    )
    max_dd = apply_registered_metric_to_blocks(
        blocks,
        portfolio,
        primitives,
        registry.get("max_dd"),
        registry.extractors["max_dd"],
        report,
        candidate_index,
    )
    sharpe_ratio = apply_registered_metric_to_blocks(
        blocks,
        portfolio,
        primitives,
        registry.get("sharpe_ratio"),
        registry.extractors["sharpe_ratio"],
        report,
        candidate_index,
    )
    ulcer_performance = apply_registered_metric_to_blocks(
        blocks,
        portfolio,
        primitives,
        registry.get("ulcer_performance_index"),
        registry.extractors["ulcer_performance_index"],
        report,
        candidate_index,
    )

    np.testing.assert_allclose(
        total_return.to_numpy(),
        [[16.56664627673854, -3.499485569102845e-05], [8.283333333333353, -3.8979529013390857]],
        rtol=1e-12,
    )
    np.testing.assert_allclose(
        max_dd.to_numpy(),
        [[6.672012977575403, 26.688043749880286], [3.7053505261597564, 14.82140210463908]],
        rtol=1e-12,
    )
    np.testing.assert_allclose(
        sharpe_ratio.to_numpy(),
        [[5.773550774826662, 0.8713601880923124], [5.445579593973149, -1.8155061328376416]],
        rtol=1e-12,
    )
    np.testing.assert_allclose(
        ulcer_performance.to_numpy(),
        [[10150681.389950285, -0.00012065699730236059], [37352.91230874136, -8.614869090555858]],
        rtol=1e-12,
    )


def test_moving_analysis_boundary_does_not_change_continuous_records_or_state() -> None:
    replay = _continuous_portfolio()
    values_before = replay.portfolio.value.copy()
    positions_before = replay.portfolio.assets.copy()
    cash_before = replay.portfolio.cash.copy()
    orders_before = replay.portfolio.orders.records_readable.copy()
    trades_before = replay.portfolio.trades.records_readable.copy()
    registry = make_metric_registry_for(())
    candidate_index = pd.MultiIndex.from_tuples([("a",), ("b",)], names=["candidate"])
    primitives = FullPathPrimitives.from_portfolio(replay.portfolio)
    _apply_total_return(replay, primitives, registry, candidate_index, [(1, 4), (4, 8)])
    _apply_total_return(replay, primitives, registry, candidate_index, [(1, 5), (5, 8)])

    pd.testing.assert_frame_equal(replay.portfolio.value, values_before)
    pd.testing.assert_frame_equal(replay.portfolio.assets, positions_before)
    pd.testing.assert_frame_equal(replay.portfolio.cash, cash_before)
    pd.testing.assert_frame_equal(replay.portfolio.orders.records_readable, orders_before)
    pd.testing.assert_frame_equal(replay.portfolio.trades.records_readable, trades_before)
