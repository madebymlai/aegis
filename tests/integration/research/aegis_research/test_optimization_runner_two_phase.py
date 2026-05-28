"""Two-phase runner contract: Splitter.apply selection sweep + held-out validation.

Exercises ``execute_optimization`` end to end with a deterministic synthetic
pipeline and asserts it returns an ``OptimizationResult`` whose three
representative candidates carry correct per-split selection and held-out
metrics.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration.schema import (
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    RunSplitConfig,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from research.aegis_research.optimization.runner import execute_optimization
from research.aegis_research.optimization.source import OptimizationSource

N_ROWS = 24
IS_LENGTH = 8  # length=8, split=0.5 -> 4-row selection + 4-row held_out per split


def _uptrend_close() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=N_ROWS, freq="D")
    levels = 100.0 * (1.01 ** np.arange(N_ROWS))
    return pd.DataFrame({"SYN": levels}, index=index)


def _exposure_pipeline(close: pd.DataFrame, n_combos: int, **param_lists):
    """Each candidate buys ``alpha`` exposure of SYN on the first bar and holds.

    Returns wide filled allocations with candidate-major MultiIndex columns
    ``[alpha, symbol]`` — higher alpha means higher exposure, so in an uptrend
    total_return is strictly monotonic in alpha.
    """
    alphas = param_lists["alpha"]
    symbols = list(close.columns)
    columns = pd.MultiIndex.from_tuples(
        [(alpha, symbol) for alpha in alphas for symbol in symbols],
        names=["alpha", "symbol"],
    )
    data = np.full((len(close), len(columns)), np.nan)
    for candidate_idx, alpha in enumerate(alphas):
        for symbol_idx in range(len(symbols)):
            data[0, candidate_idx * len(symbols) + symbol_idx] = alpha / len(symbols)
    return pd.DataFrame(data, index=close.index, columns=columns)


def _source(alphas: list[float]) -> OptimizationSource:
    return OptimizationSource(
        pipeline=_exposure_pipeline,
        params={"alpha": vbt.Param(alphas)},
        output_name="target_weights",
        evidence={"source": "synthetic_exposure"},
        diagnostics={},
        metadata={},
    )


def _optimization() -> OptimizationConfig:
    return OptimizationConfig(
        search="grid",
        split=RunSplitConfig(method="from_rolling", params={"length": IS_LENGTH, "split": 0.5}),
    )


def _run(alphas: list[float], *, min_weight: float = 0.3) -> OptimizationResult:
    return execute_optimization(
        close=_uptrend_close(),
        source=_source(alphas),
        optimization=_optimization(),
        portfolio=PortfolioConfig(fees=0.0, slippage=0.0),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", min_weight=min_weight),
    )


def _expected_split_labels() -> list[int]:
    splitter = vbt.Splitter.from_rolling(
        _uptrend_close().index, length=IS_LENGTH, split=0.5, offset=0,
        set_labels=["selection", "held_out"],
    )
    return list(splitter.get_split_labels())


def test_runner_returns_three_representative_candidates_with_per_split_metrics() -> None:
    result = _run([0.2, 0.5, 1.0])

    assert isinstance(result, OptimizationResult)
    for candidate in (result.best, result.median, result.worst):
        assert isinstance(candidate, EvaluatedCandidate)

    split_labels = _expected_split_labels()
    assert len(split_labels) >= 3

    # Phase 1 populates selection metrics for every split.
    assert set(result.best.selection_metrics) == set(split_labels)
    # Phase 3 populates held-out metrics for every split.
    assert set(result.best.held_out_metrics) == set(split_labels)

    for split_label in split_labels:
        assert "total_return" in result.best.selection_metrics[split_label]
        assert "total_return" in result.best.held_out_metrics[split_label]
        assert result.best.selection_metrics[split_label]["total_return"] is not None
        assert result.best.held_out_metrics[split_label]["total_return"] is not None


def test_runner_ranks_highest_exposure_best_and_lowest_worst() -> None:
    result = _run([0.2, 0.5, 1.0])

    # Uptrend + zero costs: total_return is monotonic in alpha exposure.
    assert result.best.params == {"alpha": 1.0}
    assert result.worst.params == {"alpha": 0.2}
    assert result.median.params == {"alpha": 0.5}
    assert result.best.score > result.median.score > result.worst.score


def test_runner_selection_and_held_out_windows_differ() -> None:
    result = _run([0.2, 0.5, 1.0])

    split_labels = _expected_split_labels()
    # Selection and held-out cover different (non-overlapping) bars, so the
    # per-split return for the same candidate differs between the two sets.
    differs = [
        result.best.selection_metrics[s]["total_return"]
        != result.best.held_out_metrics[s]["total_return"]
        for s in split_labels
    ]
    assert any(differs)


def test_runner_single_candidate_fills_all_three_slots() -> None:
    result = _run([0.7])

    assert result.best.params == {"alpha": 0.7}
    assert result.median.params == {"alpha": 0.7}
    assert result.worst.params == {"alpha": 0.7}
    # Held-out validation still runs for the deduplicated single candidate.
    split_labels = _expected_split_labels()
    assert set(result.best.held_out_metrics) == set(split_labels)
