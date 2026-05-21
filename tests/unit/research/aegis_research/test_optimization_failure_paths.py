from __future__ import annotations

import math

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
from research.aegis_research.optimization.evidence import candidate_rows_from_param_index
from research.aegis_research.optimization.leaderboard import build_optimization_leaderboard
from research.aegis_research.optimization.runner import (
    METRIC_INDEX_NAME,
    OptimizationRunnerError,
    _build_selection_function,
    execute_optimization,
)
from research.aegis_research.optimization.source import OptimizationSource


def _close_open_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2024-01-01", periods=40, freq="D")
    rng = np.random.default_rng(7)
    levels = 100 + np.cumsum(rng.normal(0.0, 1.0, size=len(index)))
    close = pd.DataFrame({"SYN": levels}, index=index)
    open_prices = close.shift(1).bfill() + 0.1
    return close, open_prices


def _optimization_config() -> OptimizationConfig:
    return OptimizationConfig(
        search="grid",
        split=RunSplitConfig(method="from_rolling", params={"length": 20, "split": 0.5}),
        random_subset=None,
        seed=None,
        execute={},
        evidence=OptimizationEvidenceConfig(return_grid="off"),
    )


def test_runner_wraps_vbt_no_results_exception_as_runner_error() -> None:
    close, open_prices = _close_open_frames()

    def always_skip(close_slice, fast_window):
        return vbt.NoResult

    source = OptimizationSource(
        pipeline=always_skip,
        params={"fast_window": vbt.Param([2, 5])},
        evidence={"source": "always_skip"},
        diagnostics={},
        metadata={},
    )

    with pytest.raises(OptimizationRunnerError, match="no usable results"):
        execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=_optimization_config(),
            portfolio=PortfolioConfig(fees=0, slippage=0),
            signal=SignalConfig(),
            report=ReportConfig(),
            ranking=RankingConfig(metric="total_return", direction="desc"),
        )


def test_selection_function_rejects_all_nan_metrics_with_visible_diagnostic() -> None:
    selection = _build_selection_function(ranking_metric="total_return", direction="desc")
    grid = pd.Series(
        [float("nan"), float("nan"), float("nan")],
        index=pd.MultiIndex.from_tuples(
            [(2, "total_return"), (5, "total_return"), (10, "total_return")],
            names=["fast_window", METRIC_INDEX_NAME],
        ),
        name="value",
    )

    with pytest.raises(OptimizationRunnerError, match="non-finite"):
        selection(grid)


def test_selection_function_picks_finite_winner_even_when_some_rows_are_nan() -> None:
    selection = _build_selection_function(ranking_metric="total_return", direction="desc")
    grid = pd.Series(
        [float("nan"), 0.30, 0.10],
        index=pd.MultiIndex.from_tuples(
            [(2, "total_return"), (5, "total_return"), (10, "total_return")],
            names=["fast_window", METRIC_INDEX_NAME],
        ),
        name="value",
    )

    label_sel = selection(grid)
    assert label_sel.value == [5]


def test_runner_pipeline_runtime_error_surfaces_to_caller() -> None:
    close, open_prices = _close_open_frames()

    def exploding_pipeline(close_slice, fast_window):
        raise RuntimeError("pipeline blew up while running")

    source = OptimizationSource(
        pipeline=exploding_pipeline,
        params={"fast_window": vbt.Param([2, 5])},
        evidence={"source": "exploding"},
        diagnostics={},
        metadata={},
    )

    with pytest.raises(RuntimeError, match="pipeline blew up"):
        execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=_optimization_config(),
            portfolio=PortfolioConfig(fees=0, slippage=0),
            signal=SignalConfig(),
            report=ReportConfig(),
            ranking=RankingConfig(metric="total_return", direction="desc"),
        )


def _selection_series_with_missing_metric(
    *,
    winner_params: tuple[int, int],
    available_metrics: dict[str, float],
) -> pd.Series:
    rows = []
    values = []
    for set_label in ("selection", "held_out"):
        for metric_name, value in available_metrics.items():
            rows.append((0, set_label, *winner_params, metric_name))
            values.append(value)
    index = pd.MultiIndex.from_tuples(
        rows,
        names=["split", "set", "fast_window", "slow_window", METRIC_INDEX_NAME],
    )
    return pd.Series(values, index=index, name="value")


def test_leaderboard_records_failure_when_winner_ranking_metric_missing() -> None:
    selection = _selection_series_with_missing_metric(
        winner_params=(5, 10),
        available_metrics={"max_dd": 0.1, "sharpe_ratio": 1.2},
    )
    sampled_index = pd.MultiIndex.from_tuples(
        [(5, 10), (2, 20)], names=["fast_window", "slow_window"]
    )
    candidate_rows = candidate_rows_from_param_index(
        sampled_index, source_identity={"source": "test"}
    )

    leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts={0: 10},
        ranking_metric="total_return",
        ranking_direction="desc",
    )

    failure_messages = [sample["message"] for sample in leaderboard["failure_samples"]]
    assert any("ranking metric" in msg and "unavailable" in msg for msg in failure_messages), (
        f"missing ranking metric should surface in failure_samples; got {failure_messages}"
    )
    assert leaderboard["rows"], "winner row should still be recorded with None ranking value"
    top = leaderboard["rows"][0]
    assert top["ranking_metric_value"] is None
    assert top["metrics"]["max_dd"] == pytest.approx(0.1)


def test_leaderboard_skips_split_with_zero_held_out_rows_and_records_failure() -> None:
    selection = _selection_series_with_missing_metric(
        winner_params=(5, 10),
        available_metrics={"total_return": 0.15},
    )
    sampled_index = pd.MultiIndex.from_tuples([(5, 10)], names=["fast_window", "slow_window"])
    candidate_rows = candidate_rows_from_param_index(
        sampled_index, source_identity={"source": "test"}
    )

    leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts={0: 0},
        ranking_metric="total_return",
        ranking_direction="desc",
    )

    failure_messages = [sample["message"] for sample in leaderboard["failure_samples"]]
    assert any("zero held-out row count" in msg for msg in failure_messages), failure_messages
    assert leaderboard["rows"] == [], (
        "no leaderboard rows should be emitted when every split has zero held-out evidence"
    )


def test_leaderboard_nan_held_out_metric_does_not_inflate_aggregate() -> None:
    rows = []
    values = []
    for split_idx in (0, 1):
        for set_label in ("selection", "held_out"):
            rows.append((split_idx, set_label, 5, 10, "total_return"))
            if set_label == "held_out" and split_idx == 1:
                values.append(float("nan"))
            else:
                values.append(0.20 if split_idx == 0 else 0.10)
    index = pd.MultiIndex.from_tuples(
        rows,
        names=["split", "set", "fast_window", "slow_window", METRIC_INDEX_NAME],
    )
    selection = pd.Series(values, index=index, name="value")
    sampled_index = pd.MultiIndex.from_tuples([(5, 10)], names=["fast_window", "slow_window"])
    candidate_rows = candidate_rows_from_param_index(
        sampled_index, source_identity={"source": "test"}
    )

    leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts={0: 10, 1: 10},
        ranking_metric="total_return",
        ranking_direction="desc",
    )

    assert len(leaderboard["rows"]) == 1
    row = leaderboard["rows"][0]
    assert math.isclose(row["ranking_metric_value"], 0.20), (
        "NaN held-out metric must be dropped from the weighted average, not coerced to 0"
    )
    assert row["oos_metric_values"] == [0.20]
    failure_messages = [sample["message"] for sample in leaderboard["failure_samples"]]
    assert any("ranking metric" in msg and "unavailable" in msg for msg in failure_messages), (
        failure_messages
    )
