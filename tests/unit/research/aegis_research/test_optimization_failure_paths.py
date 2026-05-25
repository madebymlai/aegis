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
    OptimizationRunnerError,
    _build_selection_function,
    execute_optimization,
)
from research.aegis_research.optimization.source import OptimizationSource

DATA_IDENTITY = {"source": "test", "symbols": ["SYN"], "timeframe": "1D"}


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
        output_name="active",
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
            mono_chunk_len=10000,
        )


def test_selection_function_rejects_all_nan_metrics_with_visible_diagnostic() -> None:
    selection = _build_selection_function(ranking_metric="total_return", direction="desc")
    grid = pd.DataFrame(
        {"total_return": [float("nan"), float("nan"), float("nan")]},
        index=pd.Index([2, 5, 10], name="fast_window"),
    )

    with pytest.raises(OptimizationRunnerError, match="non-finite"):
        selection(grid)


def test_selection_function_picks_finite_winner_even_when_some_rows_are_nan() -> None:
    selection = _build_selection_function(ranking_metric="total_return", direction="desc")
    grid = pd.DataFrame(
        {"total_return": [float("nan"), 0.30, 0.10]},
        index=pd.Index([2, 5, 10], name="fast_window"),
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
        output_name="active",
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
            mono_chunk_len=10000,
        )


def _selection_dataframe_with_missing_metric(
    *,
    winner_params: tuple[int, int],
    available_metrics: dict[str, float],
) -> pd.DataFrame:
    rows = []
    for set_label in ("selection", "held_out"):
        rows.append((0, set_label, *winner_params))
    index = pd.MultiIndex.from_tuples(
        rows,
        names=["split", "set", "fast_window", "slow_window"],
    )
    return pd.DataFrame([available_metrics] * len(rows), index=index)


def test_leaderboard_records_failure_when_winner_ranking_metric_missing() -> None:
    selection = _selection_dataframe_with_missing_metric(
        winner_params=(5, 10),
        available_metrics={"max_dd": 0.1, "sharpe_ratio": 1.2},
    )
    sampled_index = pd.MultiIndex.from_tuples(
        [(5, 10), (2, 20)], names=["fast_window", "slow_window"]
    )
    candidate_rows = candidate_rows_from_param_index(
        sampled_index,
        source_identity={"source": "test"},
        data_identity=DATA_IDENTITY,
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
    selection = _selection_dataframe_with_missing_metric(
        winner_params=(5, 10),
        available_metrics={"total_return": 0.15},
    )
    sampled_index = pd.MultiIndex.from_tuples([(5, 10)], names=["fast_window", "slow_window"])
    candidate_rows = candidate_rows_from_param_index(
        sampled_index,
        source_identity={"source": "test"},
        data_identity=DATA_IDENTITY,
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
    metric_rows = []
    for split_idx in (0, 1):
        for set_label in ("selection", "held_out"):
            rows.append((split_idx, set_label, 5, 10))
            if set_label == "held_out" and split_idx == 1:
                metric_rows.append({"total_return": float("nan")})
            else:
                metric_rows.append({"total_return": 0.20 if split_idx == 0 else 0.10})
    index = pd.MultiIndex.from_tuples(
        rows,
        names=["split", "set", "fast_window", "slow_window"],
    )
    selection = pd.DataFrame(metric_rows, index=index)
    sampled_index = pd.MultiIndex.from_tuples([(5, 10)], names=["fast_window", "slow_window"])
    candidate_rows = candidate_rows_from_param_index(
        sampled_index,
        source_identity={"source": "test"},
        data_identity=DATA_IDENTITY,
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


def test_leaderboard_canonical_key_supports_nan_and_complex_param_values() -> None:
    rows = []
    metric_rows = []
    for set_label in ("selection", "held_out"):
        rows.append((0, set_label, float("nan"), 0.10))
        metric_rows.append({"total_return": 0.20 if set_label == "selection" else 0.15})
    index = pd.MultiIndex.from_tuples(
        rows, names=["split", "set", "sl_stop", "tp_stop"]
    )
    selection = pd.DataFrame(metric_rows, index=index)
    sampled_index = pd.MultiIndex.from_tuples(
        [(float("nan"), 0.10)], names=["sl_stop", "tp_stop"]
    )
    candidate_rows = candidate_rows_from_param_index(
        sampled_index,
        source_identity={"source": "test"},
        data_identity=DATA_IDENTITY,
    )

    leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts={0: 10},
        ranking_metric="total_return",
        ranking_direction="desc",
    )

    assert leaderboard["rows"], "winner with NaN-valued param must produce a leaderboard row"
    assert leaderboard["rows"][0]["candidate_key"] == candidate_rows[0]["candidate_key"]


def test_leaderboard_none_ranking_metric_sorts_last_for_both_directions() -> None:
    rows = []
    metric_rows = []
    for split_idx, params, held_out_ret in (
        (0, (2, 10), 0.10),
        (1, (5, 20), 0.30),
        (2, (10, 50), float("nan")),
    ):
        rows.append((split_idx, "selection", *params))
        metric_rows.append({"total_return": held_out_ret if not (isinstance(held_out_ret, float) and math.isnan(held_out_ret)) else 0.0})
        rows.append((split_idx, "held_out", *params))
        metric_rows.append({"total_return": held_out_ret})
    index = pd.MultiIndex.from_tuples(
        rows,
        names=["split", "set", "fast_window", "slow_window"],
    )
    selection = pd.DataFrame(metric_rows, index=index)
    sampled_index = pd.MultiIndex.from_tuples(
        [(2, 10), (5, 20), (10, 50)], names=["fast_window", "slow_window"]
    )
    candidate_rows = candidate_rows_from_param_index(
        sampled_index,
        source_identity={"source": "test"},
        data_identity=DATA_IDENTITY,
    )

    desc_leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts={0: 10, 1: 10, 2: 10},
        ranking_metric="total_return",
        ranking_direction="desc",
    )
    asc_leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts={0: 10, 1: 10, 2: 10},
        ranking_metric="total_return",
        ranking_direction="asc",
    )

    assert len(desc_leaderboard["rows"]) == 3
    assert desc_leaderboard["rows"][-1]["ranking_metric_value"] is None, (
        "desc: None ranking value must sort last"
    )
    assert asc_leaderboard["rows"][-1]["ranking_metric_value"] is None, (
        "asc: None ranking value must sort last (regression — was previously sorting first)"
    )
