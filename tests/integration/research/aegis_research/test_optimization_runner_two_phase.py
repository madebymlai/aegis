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
from research.aegis_research.optimization.precompute import (
    WideIndicatorPrecompute,
    build_candidate_index,
    empty_precompute,
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


def _exposure_simulate(close: pd.DataFrame, indicator_window, n_combos: int, **param_lists):
    """Each candidate buys ``alpha`` exposure of SYN on the first bar and holds.

    This is a strategy-only source (no indicators), so it ignores the windowed
    indicator outputs and computes allocations directly from the price window.
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
        precompute=empty_precompute,
        simulate=_exposure_simulate,
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
        open_=_uptrend_close(),
        source=_source(alphas),
        optimization=_optimization(),
        portfolio=PortfolioConfig(fees=0.0, slippage=0.0, direction="longonly"),
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


def test_runner_preserves_excluded_degenerate_through_held_out(monkeypatch) -> None:
    """The held-out phase rebuilds the OptimizationResult; the degenerate-exclusion
    count from the selection ranking must survive that round-trip.

    The synthetic pipeline can't produce NaN-scored (degenerate) candidates — a
    zero-allocation candidate still scores a finite 0.0 — so we inject a known
    exclusion count at the ranking boundary and assert the runner threads it
    through ``_attach_held_out`` unchanged.
    """
    import dataclasses

    from research.aegis_research.optimization import runner

    real_select = runner.select_representative_candidates

    def select_with_injected_exclusions(grid, verdicts, **kwargs):
        result = real_select(grid, verdicts, **kwargs)
        return dataclasses.replace(result, excluded_degenerate=7)

    monkeypatch.setattr(runner, "select_representative_candidates", select_with_injected_exclusions)

    result = _run([0.2, 0.5, 1.0])

    assert result.excluded_degenerate == 7
    # Held-out validation still populated, proving the round-trip really ran.
    assert set(result.best.held_out_metrics) == set(_expected_split_labels())


def test_runner_preserves_total_candidates_through_held_out(monkeypatch) -> None:
    """The exact ranked-set size must survive the held-out round-trip too.

    ``_attach_held_out`` rebuilds the frozen OptimizationResult; the exact
    Candidate total (size of the ranked set) the ranking layer computed must be
    carried forward, exactly as the degenerate-exclusion count is.
    """
    import dataclasses

    from research.aegis_research.optimization import runner

    real_select = runner.select_representative_candidates

    def select_with_injected_total(grid, verdicts, **kwargs):
        result = real_select(grid, verdicts, **kwargs)
        return dataclasses.replace(result, total_candidates=11)

    monkeypatch.setattr(runner, "select_representative_candidates", select_with_injected_total)

    result = _run([0.2, 0.5, 1.0])

    assert result.total_candidates == 11
    # Held-out validation still populated, proving the round-trip really ran.
    assert set(result.best.held_out_metrics) == set(_expected_split_labels())


def _warmup_precompute(
    close: pd.DataFrame, n_candidates: int, **param_lists
) -> WideIndicatorPrecompute:
    """Causal momentum (close[t]/close[t-window]-1); a window >= history is all-NaN."""
    windows = param_lists["window"]
    prices = close.to_numpy()
    n_rows, n_symbols = prices.shape
    outputs = np.full((n_rows, n_candidates * n_symbols), np.nan)
    for candidate, window in enumerate(windows):
        block = np.full((n_rows, n_symbols), np.nan)
        if window < n_rows:
            block[window:] = prices[window:] / prices[:-window] - 1.0
        outputs[:, candidate * n_symbols : (candidate + 1) * n_symbols] = block
    return WideIndicatorPrecompute(
        outputs={"mom": outputs},
        candidate_index=build_candidate_index(param_lists),
        n_symbols=n_symbols,
    )


def _gated_simulate(
    close_window: pd.DataFrame, indicator_window, n_candidates: int, **param_lists
) -> pd.DataFrame:
    """Buy equal-weight on the first warmup-complete bar; else hold cash (no trade)."""
    momentum = indicator_window["mom"]
    n_symbols = len(close_window.columns)
    windows = param_lists["window"]
    allocations = np.full((len(close_window), n_candidates * n_symbols), np.nan)
    for candidate in range(n_candidates):
        block = momentum[:, candidate * n_symbols : (candidate + 1) * n_symbols]
        warmup_complete = ~np.isnan(block).any(axis=1)
        if warmup_complete.any():
            first = int(np.argmax(warmup_complete))
            allocations[first, candidate * n_symbols : (candidate + 1) * n_symbols] = (
                1.0 / n_symbols
            )
    symbols = list(close_window.columns)
    columns = pd.MultiIndex.from_tuples(
        [(windows[c], sym) for c in range(n_candidates) for sym in symbols],
        names=["window", "symbol"],
    )
    return pd.DataFrame(allocations, index=close_window.index, columns=columns)


def _warmup_source(windows: list[int]) -> OptimizationSource:
    return OptimizationSource(
        precompute=_warmup_precompute,
        simulate=_gated_simulate,
        params={"window": vbt.Param(windows)},
        output_name="target_weights",
        evidence={"source": "synthetic_warmup"},
        diagnostics={},
        metadata={},
    )


def _run_warmup(windows: list[int]) -> OptimizationResult:
    return execute_optimization(
        close=_uptrend_close(),
        open_=_uptrend_close(),
        source=_warmup_source(windows),
        optimization=_optimization(),
        portfolio=PortfolioConfig(fees=0.0, slippage=0.0, direction="longonly"),
        report=ReportConfig(),
        ranking=RankingConfig(metric="total_return", min_weight=0.3),
    )


def test_held_out_and_selection_builds_receive_the_same_invalid_candidate_set(
    monkeypatch,
) -> None:
    """Both sweeps must mask the same Invalid Candidates so they cannot drift.

    A genuine Invalid Candidate (lookback exceeding full history) makes the
    Selection build's Invalid-Candidate set non-empty. The held-out build must
    receive that *same* set; on the pre-change code it receives nothing (the
    builder's optional default), so the captured sets differ.
    """
    from research.aegis_research.optimization import runner

    real_build = runner._build_precomputed_window_metrics
    captured: list[object] = []

    def spy(**kwargs):
        captured.append(kwargs.get("invalid_candidate_keys"))
        return real_build(**kwargs)

    monkeypatch.setattr(runner, "_build_precomputed_window_metrics", spy)

    _run_warmup([2, N_ROWS + 1])  # window N_ROWS+1 has no finite full-history block

    assert len(captured) == 2, "expected one selection build then one held-out build"
    selection_keys, held_out_keys = captured
    assert selection_keys, "selection build should mask a non-empty Invalid-Candidate set"
    assert held_out_keys == selection_keys, (
        "held-out build must receive the SAME Invalid-Candidate set as selection"
    )


def test_phase1_sweeps_in_parallel_with_pathos_and_phase3_runs_sequentially(monkeypatch) -> None:
    """Phase 1 distributes mono-chunks across processes via pathos; Phase 3 (the
    three held-out candidates) sweeps a single mono-chunk sequentially in-process."""
    from research.aegis_research.optimization import runner

    captured: list[dict] = []
    real_parameterized = runner.vbt.parameterized

    def spy(func, **kwargs):
        captured.append(dict(kwargs))
        # Drop the pathos engine so the assertion stays single-process and fast;
        # the mono calling convention the runner relies on is left untouched.
        stripped = {key: value for key, value in kwargs.items() if key != "execute_kwargs"}
        return real_parameterized(func, **stripped)

    monkeypatch.setattr(runner.vbt, "parameterized", spy)

    _run([0.2, 0.5, 1.0])

    assert len(captured) == 2, "expected one Phase 1 sweep then one Phase 3 sweep"
    phase1, phase3 = captured

    # Phase 1: full grid distributed across cores under pathos.
    assert phase1["mono_n_chunks"] == "auto"
    assert phase1["execute_kwargs"] == {"engine": "pathos"}

    # Phase 3: one sequential mono-chunk, no parallel engine.
    assert phase3["mono_n_chunks"] == 1
    assert "execute_kwargs" not in phase3
