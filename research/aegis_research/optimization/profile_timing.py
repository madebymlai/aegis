"""PFO-substrate timing spans for the A+B checkpoint profile.

Records wall-clock elapsed time for key optimization phases without cProfile
amplification so the post-A+B profile on the PFO substrate can be compared
against the pre-change legacy scalar + report-metric baseline.

Usage as a library::

    from research.aegis_research.optimization.profile_timing import TimingSpans

    spans = TimingSpans()
    with spans.phase("data_loading"):
        market_data = load_market_data_result(...)
    with spans.phase("pipeline_total"):
        allocations = pipeline(close_slice, n_candidates, **params)
    summary = spans.summary()

Direct execution::

    python -m research.aegis_research.optimization.profile_timing

Runs a synthetic benchmark that exercises the full PFO path with
deterministic data so wall-clock measurements are reproducible.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
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
from research.aegis_research.optimization.runner import OptimizationRun, execute_optimization
from research.aegis_research.optimization.source import OptimizationSource

DEFAULT_BARS = 500
DEFAULT_SYMBOLS = 3
DEFAULT_CANDIDATES = 20
DEFAULT_SPLITS = 3
DEFAULT_SPLIT_WINDOW = 126

PFO_PROFILE_SCHEMA_VERSION = "pfo_profile.v1"


@dataclass
class PhaseTiming:
    name: str
    elapsed_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimingSpans:
    phases: list[PhaseTiming] = field(default_factory=list)
    _start_stack: list[float] = field(default_factory=list)

    @contextlib.contextmanager
    def phase(self, name: str, **metadata: Any):
        self._start_stack.append(time.perf_counter())
        try:
            yield
        finally:
            elapsed = time.perf_counter() - self._start_stack.pop()
            self.phases.append(
                PhaseTiming(name=name, elapsed_seconds=elapsed, metadata=dict(metadata))
            )

    def summary(self) -> dict[str, Any]:
        total = sum(p.elapsed_seconds for p in self.phases)
        by_name: dict[str, float] = {}
        for p in self.phases:
            by_name[p.name] = by_name.get(p.name, 0.0) + p.elapsed_seconds
        return {
            "schema_version": PFO_PROFILE_SCHEMA_VERSION,
            "total_seconds": total,
            "phase_seconds": dict(sorted(by_name.items(), key=lambda kv: -kv[1])),
            "phase_pct": {
                name: round(seconds / total * 100, 2) if total > 0 else 0.0
                for name, seconds in by_name.items()
            },
            "phases": [
                {
                    "name": p.name,
                    "elapsed_seconds": p.elapsed_seconds,
                    "metadata": p.metadata,
                }
                for p in self.phases
            ],
        }


def build_synthetic_close(
    *,
    n_bars: int = DEFAULT_BARS,
    n_symbols: int = DEFAULT_SYMBOLS,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2020-01-01", periods=n_bars, freq="D")
    prices = 100.0 + np.cumsum(rng.normal(0.0, 1.0, size=(n_bars, n_symbols)), axis=0)
    symbols = [f"SYM_{i}" for i in range(n_symbols)]
    return pd.DataFrame(prices, index=index, columns=symbols)


def build_synthetic_source(
    *,
    n_candidates: int = DEFAULT_CANDIDATES,
    n_symbols: int = DEFAULT_SYMBOLS,
    seed: int = 7,
) -> OptimizationSource:
    rng = np.random.default_rng(seed)
    windows = rng.integers(5, 50, size=n_candidates).tolist()
    thresholds = rng.uniform(0.3, 0.7, size=n_candidates).tolist()

    def pipeline(close_slice: pd.DataFrame, n_candidates: int, **param_lists: Any) -> pd.DataFrame:
        w = param_lists["window"]
        thresh = param_lists["threshold"]
        symbols = close_slice.columns
        n_symbols = len(symbols)
        n_bars_in = len(close_slice)
        alloc_arr = np.full((n_bars_in, n_candidates * n_symbols), np.nan)
        for i in range(n_candidates):
            ma = close_slice.rolling(int(w[i]), min_periods=1).mean()
            price_ratio = close_slice.div(ma)
            selected = price_ratio > thresh[i]
            n_sel = selected.sum(axis=1).clip(lower=1)
            weights = selected.div(n_sel, axis=0).astype(float)
            alloc_arr[:, i * n_symbols : (i + 1) * n_symbols] = weights.values
        param_names = sorted(param_lists)
        col_tuples = []
        for i in range(n_candidates):
            for sym in symbols:
                col_tuples.append(tuple(param_lists[k][i] for k in param_names) + (sym,))
        col_mi = pd.MultiIndex.from_tuples(col_tuples, names=param_names + ["symbol"])
        return pd.DataFrame(alloc_arr, index=close_slice.index, columns=col_mi)

    return OptimizationSource(
        pipeline=pipeline,
        params={
            "window": vbt.Param(windows),
            "threshold": vbt.Param(thresholds),
        },
        output_name="active",
        evidence={"source": "synthetic_pfo_profile"},
        diagnostics={},
        metadata={},
    )


def build_profile_config(
    *,
    n_splits: int = DEFAULT_SPLITS,
    split_window: int = DEFAULT_SPLIT_WINDOW,
    search: str = "grid",
    random_subset: int | None = None,
    seed: int | None = 11,
) -> OptimizationConfig:
    return OptimizationConfig(
        search=search,
        split=RunSplitConfig(
            method="from_rolling",
            params={"length": split_window, "split": 0.5},
            max_splits=n_splits,
        ),
        random_subset=random_subset,
        seed=seed,
        execute={},
        evidence=OptimizationEvidenceConfig(return_grid="off"),
    )


def run_pfo_profile(
    *,
    n_bars: int = DEFAULT_BARS,
    n_symbols: int = DEFAULT_SYMBOLS,
    n_candidates: int = DEFAULT_CANDIDATES,
    n_splits: int = DEFAULT_SPLITS,
    split_window: int = DEFAULT_SPLIT_WINDOW,
    search: str = "grid",
    random_subset: int | None = None,
    profile_seed: int = 11,
    data_seed: int = 42,
    source_seed: int = 7,
    fees: float = 0.001,
    slippage: float = 0.0005,
) -> tuple[dict[str, Any], OptimizationRun]:
    spans = TimingSpans()

    with spans.phase("data_generation"):
        close = build_synthetic_close(
            n_bars=n_bars, n_symbols=n_symbols, seed=data_seed,
        )
        open_prices = close.shift(1).bfill() + 0.01

    with spans.phase("source_construction"):
        source = build_synthetic_source(
            n_candidates=n_candidates, n_symbols=n_symbols, seed=source_seed,
        )

    with spans.phase("optimization_config"):
        optimization = build_profile_config(
            n_splits=n_splits, split_window=split_window,
            search=search, random_subset=random_subset, seed=profile_seed,
        )
        portfolio = PortfolioConfig(fees=fees, slippage=slippage)
        signal = SignalConfig()
        report = ReportConfig()
        ranking = RankingConfig(metric="total_return", direction="desc")

    with spans.phase("execute_optimization"):
        run = execute_optimization(
            close=close,
            open_prices=open_prices,
            source=source,
            optimization=optimization,
            portfolio=portfolio,
            signal=signal,
            report=report,
            ranking=ranking,
            mono_chunk_len=n_candidates,
        )

    with spans.phase("evidence_extraction"):
        selection = run.selection
        n_winners = len(selection.xs("selection", level="set"))
        sampled_count = len(run.sampled_index)

    evidence_phase = spans.phases[-1]
    evidence_phase.metadata.update(n_winners=n_winners, sampled_count=sampled_count)

    summary = spans.summary()
    summary["config"] = {
        "n_bars": n_bars,
        "n_symbols": n_symbols,
        "n_candidates": n_candidates,
        "n_splits": n_splits,
        "split_window": split_window,
        "search": search,
        "random_subset": random_subset,
        "seed": profile_seed,
    }
    return summary, run


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="PFO substrate timing profile")
    parser.add_argument("--bars", type=int, default=DEFAULT_BARS)
    parser.add_argument("--symbols", type=int, default=DEFAULT_SYMBOLS)
    parser.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES)
    parser.add_argument("--splits", type=int, default=DEFAULT_SPLITS)
    parser.add_argument("--split-window", type=int, default=DEFAULT_SPLIT_WINDOW)
    parser.add_argument("--search", choices=["grid", "random"], default="grid")
    parser.add_argument("--random-subset", type=int, default=None)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--json", action="store_true", default=False)
    args = parser.parse_args()

    summary, _run = run_pfo_profile(
        n_bars=args.bars,
        n_symbols=args.symbols,
        n_candidates=args.candidates,
        n_splits=args.splits,
        split_window=args.split_window,
        search=args.search,
        random_subset=args.random_subset,
        profile_seed=args.seed,
    )

    if args.json:
        json.dump(summary, sys.stdout, indent=2, default=str)
    else:
        print(f"Total: {summary['total_seconds']:.3f}s")
        for name, seconds in summary["phase_seconds"].items():
            pct = summary["phase_pct"][name]
            print(f"  {name}: {seconds:.3f}s ({pct:.1f}%)")


if __name__ == "__main__":
    main()
