"""Two-phase runner contract: Splitter.apply selection sweep + held-out validation.

Exercises ``execute_optimization`` end to end with a deterministic synthetic
pipeline and asserts it returns an ``OptimizationResult`` whose three
representative candidates carry correct per-split selection and held-out
metrics.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration import OptimizationConfig
from research.aegis_research.metrics import make_default_metric_registry
from research.aegis_research.optimization.precompute import (
    IndicatorPrecompute,
    build_candidate_index,
    empty_precompute,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from research.aegis_research.optimization.runner import execute_optimization
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.optimization.window_evaluation import ResolvedBook
from research.aegis_research.run_splits import build_run_splits_result
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_portfolio_config,
    make_ranking_config,
    make_report_config,
    make_run_arrays,
    make_run_split_config,
)

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
    Returns filled allocations with candidate-major MultiIndex columns
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
        resolve_lookbacks=lambda params: {"source": 0},
        params={"alpha": vbt.Param(alphas)},
        output_name="target_weights",
        evidence={"source": "synthetic_exposure"},
        diagnostics={},
        metadata={},
    )


def _optimization() -> OptimizationConfig:
    return make_optimization_config(
        search="grid",
        split=make_run_split_config(method="from_rolling", params={"length": IS_LENGTH, "split": 0.5}),
    )


def _run(alphas: list[float]) -> OptimizationResult:
    optimization = _optimization()
    return execute_optimization(
        arrays=make_run_arrays(close=_uptrend_close(), open_=_uptrend_close()),
        source=_source(alphas),
        optimization=optimization,
        book=ResolvedBook(make_portfolio_config(fees=0.0, slippage=0.0, direction="longonly")),
        report=make_report_config(),
        ranking=make_ranking_config(metric="total_return"),
        metric_registry=make_default_metric_registry(),
        split_result=build_run_splits_result(_uptrend_close().index, optimization.split),
    )


class _RecordingSplitter:
    """Delegates to the real built Splitter while recording each ``set_`` role."""

    def __init__(self, inner: vbt.Splitter) -> None:
        self._inner = inner
        self.applied_sets: list[str] = []

    def apply(self, *args, set_: str, **kwargs):
        self.applied_sets.append(set_)
        return self._inner.apply(*args, set_=set_, **kwargs)


def test_runner_consumes_the_injected_splitter_and_addresses_sets_by_role() -> None:
    """The runner must run its selection sweep on the selection set and its
    held-out sweep on the held-out set through the injected Splitter — proving
    role assignment lives in run_splits and the runner performs no rebuild."""
    optimization = _optimization()
    split_result = build_run_splits_result(_uptrend_close().index, optimization.split)
    recorder = _RecordingSplitter(split_result.splitter)

    execute_optimization(
        arrays=make_run_arrays(close=_uptrend_close(), open_=_uptrend_close()),
        source=_source([0.2, 0.5, 1.0]),
        optimization=optimization,
        book=ResolvedBook(make_portfolio_config(fees=0.0, slippage=0.0, direction="longonly")),
        report=make_report_config(),
        ranking=make_ranking_config(metric="total_return"),
        metric_registry=make_default_metric_registry(),
        split_result=dataclasses.replace(split_result, splitter=recorder),
    )

    assert recorder.applied_sets == ["selection", "held_out"]


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
    # score is the Friedman mean rank: lower is better, so best < median < worst.
    assert result.best.score < result.median.score < result.worst.score


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
    through the held-out attachment unchanged.
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

    The held-out attachment rebuilds the frozen OptimizationResult; the exact
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
) -> IndicatorPrecompute:
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
    return IndicatorPrecompute(
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
        resolve_lookbacks=lambda params: {"source": int(params["window"])},
        params={"window": vbt.Param(windows)},
        output_name="target_weights",
        evidence={"source": "synthetic_warmup"},
        diagnostics={},
        metadata={},
    )


def _run_warmup(windows: list[int]) -> OptimizationResult:
    optimization = _optimization()
    return execute_optimization(
        arrays=make_run_arrays(close=_uptrend_close(), open_=_uptrend_close()),
        source=_warmup_source(windows),
        optimization=optimization,
        book=ResolvedBook(make_portfolio_config(fees=0.0, slippage=0.0, direction="longonly")),
        report=make_report_config(),
        ranking=make_ranking_config(metric="total_return"),
        metric_registry=make_default_metric_registry(),
        split_result=build_run_splits_result(_uptrend_close().index, optimization.split),
    )


def test_selection_and_held_out_sweeps_share_one_evaluator_carrying_the_invalid_set(
    monkeypatch,
) -> None:
    """Both sweeps must run through the same WindowEvaluator so they cannot drift.

    A genuine Invalid Candidate (lookback exceeding full history) makes the
    evaluator's Invalid-Candidate set non-empty. Selection and held-out are
    handed the *same* evaluator object, so the set they exclude by is identical
    by construction — asserted here via the evaluator bound to each sweep.
    """
    from research.aegis_research.optimization import runner

    real_sweep = runner._sweep
    captured: list[object] = []

    def spy(*, candidate_metrics, **kwargs):
        captured.append(candidate_metrics)
        return real_sweep(candidate_metrics=candidate_metrics, **kwargs)

    monkeypatch.setattr(runner, "_sweep", spy)

    _run_warmup([2, N_ROWS + 1])  # window N_ROWS+1 has no finite full-history block

    assert len(captured) == 2, "expected one selection sweep then one held-out sweep"
    selection_metrics, held_out_metrics = captured
    # ``evaluator.evaluate`` is a bound method; ``__self__`` is the evaluator itself.
    assert selection_metrics.__self__ is held_out_metrics.__self__, (
        "selection and held-out sweeps must share one evaluator"
    )
    assert selection_metrics.__self__.store.invalid_keys, (
        "the shared evaluator's store should carry a non-empty Invalid-Candidate set"
    )


def test_runner_passes_full_market_index_to_simulate_not_window_index(monkeypatch) -> None:
    """The runner must pass the full loaded-data index as market_index,
    not the window's own index. With a contiguous split method both are
    effectively the same, but with a purged split the difference is that the
    full index has gaps the window index doesn't."""
    from research.aegis_research.optimization.window_evaluation import evaluator as window_evaluator

    real_sim = window_evaluator.simulate_portfolio_batch
    captured_indices: list[pd.Index] = []

    def spy(*args, market_index, **kwargs):
        captured_indices.append(market_index)
        return real_sim(*args, market_index=market_index, **kwargs)

    monkeypatch.setattr(window_evaluator, "simulate_portfolio_batch", spy)

    _run([0.2, 0.5, 1.0])

    full_index = _uptrend_close().index
    assert len(captured_indices) > 0, (
        "expected at least one portfolio simulation through the window evaluator"
    )
    for idx in captured_indices:
        assert idx.equals(full_index), (
            f"market_index must be the full loaded-data index ({len(full_index)} rows); "
            f"got an index with {len(idx)} rows"
        )


def test_runner_records_zero_non_executable_rows_for_contiguous_split() -> None:
    """A contiguous walk-forward split has no gaps, so the seam mask never fires
    and non_executable_rows must be zero — this is an invariant monitor."""
    result = _run([0.2, 0.5, 1.0])
    assert result.non_executable_rows == 0, (
        f"contiguous split must record zero non_executable_rows; got {result.non_executable_rows}"
    )


def test_runner_records_exact_non_executable_rows_for_purged_kfold_split() -> None:
    """``non_executable_rows`` is the seam cost of the Split structure — exact,
    not merely positive, and independent of how the sweep was chunked.

    With 24 rows and 3 folds of 8, each split's *selection* window is the
    complement of one test fold. Only the middle fold's complement
    (rows 0-7 + 16-23) has an internal seam: the window jumps from row 7 to
    row 16, whose bar is not the immediate calendar successor — so exactly
    one row is non-executable across the whole structure. A chunked sweep
    that re-counts the same window per candidate chunk would inflate this —
    asserting the exact value pins the structural semantic."""
    close = _uptrend_close()
    purged_opt = make_optimization_config(
        search="grid",
        split=make_run_split_config(
            method="from_purged_kfold", params={"n_folds": 3, "n_test_folds": 1}
        ),
    )
    result = execute_optimization(
        arrays=make_run_arrays(close=close, open_=close),
        source=_source([0.2, 0.5, 1.0]),
        optimization=purged_opt,
        book=ResolvedBook(make_portfolio_config(fees=0.0, slippage=0.0, direction="longonly")),
        report=make_report_config(),
        ranking=make_ranking_config(metric="total_return"),
        metric_registry=make_default_metric_registry(),
        split_result=build_run_splits_result(close.index, purged_opt.split),
    )
    assert result.non_executable_rows == 1, (
        f"purged k-fold 3x8 structure has exactly one seam row; got {result.non_executable_rows}"
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
    assert phase1["execute_kwargs"] == {"engine": "pathos", "join_pool": True}

    # Phase 3: one sequential mono-chunk, no parallel engine.
    assert phase3["mono_n_chunks"] == 1
    assert "execute_kwargs" not in phase3
