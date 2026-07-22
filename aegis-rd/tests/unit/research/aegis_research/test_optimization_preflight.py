from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.optimization.preflight import (
    PreflightError,
    build_preflight,
)
from research.aegis_research.optimization.source import OptimizationSource
from tests.support.research.aegis_research.factories import make_optimization_config


def _source(
    params: dict[str, vbt.Param], *, lookback_param: str | None = None
) -> OptimizationSource:
    def should_not_execute(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("preflight must not execute Indicator or Portfolio work")

    def resolve(candidate: dict[str, Any]) -> dict[str, int]:
        return {"component": 2 if lookback_param is None else int(candidate[lookback_param])}

    return OptimizationSource(
        precompute=should_not_execute,
        simulate=should_not_execute,
        resolve_lookbacks=resolve,
        params=params,
        evidence={},
    )


def test_preflight_reports_continuous_replay_and_observation_block_geometry() -> None:
    source = _source(
        {
            "window": vbt.Param([2, 4]),
            "threshold": vbt.Param([0.4, 0.6]),
        },
        lookback_param="window",
    )

    result = build_preflight(
        source=source,
        optimization=make_optimization_config(observation_block_bars=6),
        index=pd.RangeIndex(20),
        symbol_count=2,
        metric_count=7,
        has_open_prices=True,
    )

    diagnostics = result.diagnostics
    assert diagnostics["schema_version"] == "optimization_preflight.v2"
    assert diagnostics["sampled_combinations"] == 4
    assert diagnostics["loaded_rows"] == 20
    assert diagnostics["derived_warmup_rows"] == 4
    assert diagnostics["scored_start"] == 4
    assert diagnostics["scored_rows"] == 16
    assert diagnostics["observation_block_bars"] == 6
    assert diagnostics["observation_block_count"] == 2
    assert diagnostics["observation_block_bounds"] == [[4, 10], [10, 20]]
    assert diagnostics["peak_candidate_batch_count"] == 4
    assert diagnostics["peak_candidate_batch_cells"] == 4 * 20 * 2 * 5
    assert diagnostics["observation_metric_cells"] == 4 * 2 * 7
    assert "limits" not in diagnostics
    assert result.blocks.bounds == ((4, 10), (10, 20))


def test_preflight_one_candidate_and_exact_minimum_two_blocks_agree() -> None:
    result = build_preflight(
        source=_source({"window": vbt.Param([2])}, lookback_param="window"),
        optimization=make_optimization_config(observation_block_bars=4),
        index=pd.RangeIndex(10),
        symbol_count=1,
        metric_count=6,
        has_open_prices=False,
    )

    assert result.plan.candidates.count == 1
    assert result.blocks.bounds == ((2, 6), (6, 10))
    assert result.diagnostics["observation_metric_cells"] == 1 * 2 * 6


def test_preflight_merges_final_remainder_into_the_last_complete_block() -> None:
    result = build_preflight(
        source=_source({"window": vbt.Param([1])}, lookback_param="window"),
        optimization=make_optimization_config(observation_block_bars=4),
        index=pd.RangeIndex(12),
        symbol_count=1,
        metric_count=6,
        has_open_prices=False,
    )

    assert result.blocks.bounds == ((1, 5), (5, 12))


def test_materialized_grid_maximum_lookback_sets_one_common_start() -> None:
    result = build_preflight(
        source=_source({"window": vbt.Param([2, 7])}, lookback_param="window"),
        optimization=make_optimization_config(observation_block_bars=4),
        index=pd.RangeIndex(20),
        symbol_count=1,
        metric_count=6,
        has_open_prices=False,
    )

    assert result.plan.lookbacks.candidate_warmup_bars == (2, 7)
    assert result.plan.lookbacks.scored_start == 7
    assert result.blocks.bounds[0][0] == 7


def test_random_preflight_uses_the_materialized_seeded_sample() -> None:
    result = build_preflight(
        source=_source({"window": vbt.Param(range(1, 101))}, lookback_param="window"),
        optimization=make_optimization_config(
            search="random",
            random_subset=3,
            seed=42,
            observation_block_bars=4,
        ),
        index=pd.RangeIndex(120),
        symbol_count=1,
        metric_count=6,
        has_open_prices=False,
    )

    assert result.plan.candidates.count == 3
    assert result.diagnostics["sampled_combinations"] == 3
    assert result.diagnostics["sampled_count_source"] == "materialized_grid"


def test_insufficient_post_warmup_history_fails_before_execution() -> None:
    source = _source({"window": vbt.Param([7])}, lookback_param="window")

    with pytest.raises(PreflightError, match="at least two") as error:
        build_preflight(
            source=source,
            optimization=make_optimization_config(observation_block_bars=4),
            index=pd.RangeIndex(14),
            symbol_count=1,
            metric_count=6,
            has_open_prices=False,
        )

    assert error.value.diagnostics["loaded_rows"] == 14
    assert error.value.diagnostics["derived_warmup_rows"] == 7
    assert error.value.diagnostics["scored_rows"] == 7
