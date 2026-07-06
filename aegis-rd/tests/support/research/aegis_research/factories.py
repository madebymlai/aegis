"""Test-construction factories for Run Config dataclasses.

Each factory supplies valid defaults for every field and accepts **overrides.
Routing construction through factories means porting one helper instead of N call
sites when section defaults change (e.g. when pydantic v2 adoption drops
gross_cap and data.arrays schema defaults).

These are test-support only — no production code changes.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.component_registry.contracts import (
    ComponentDefinition,
    ComponentFamily,
)
from research.aegis_research.component_registry.registry import (
    FrozenComponentRegistry,
    freeze_component_registry,
)
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    DataConfig,
    DataQualityConfig,
    Lock,
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    RunSplitConfig,
    SignalConfig,
)
from research.aegis_research.optimization.candidate_grid import (
    SPLIT_LEVEL,
    CandidateGrid,
)
from research.aegis_research.optimization.pipeline.setup import SetupResult
from research.aegis_research.optimization.precompute import CandidateKey


def make_data_quality_config(**overrides: Any) -> DataQualityConfig:
    """Return a DataQualityConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "allowed_degradations": [],
    }
    defaults.update(overrides)
    return DataQualityConfig(**defaults)


def make_data_config(**overrides: Any) -> DataConfig:
    """Return a DataConfig with valid defaults, overridden by any kwargs.

    ``arrays`` is field-required on the pydantic DataConfig; the factory
    supplies it as a kwarg just like every other field.
    """
    defaults: dict[str, Any] = {
        "arrays": ["OHLCV"],
        "base_currency": "EUR",
        "instruments": ["SYN.XNAS"],
        "exchange": [],
        "futures": [],
        "start": "2024-01-01",
        "end": "2024-01-03",
        "timeframe": "1D",
        "path": None,
        "missing_index": "raise",
        "missing_columns": "raise",
        "tz_localize": None,
        "tz_convert": None,
        "skip_on_error": False,
        "silence_warnings": False,
        "quality": make_data_quality_config(),
    }
    defaults.update(overrides)
    return DataConfig(**defaults)


def make_signal_config(**overrides: Any) -> SignalConfig:
    """Return a SignalConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "policy": "long_only_hysteresis",
        "long_entry_threshold": 0.55,
        "long_exit_threshold": 0.50,
        "execution_timing": "next_open",
    }
    defaults.update(overrides)
    return SignalConfig(**defaults)


def make_portfolio_config(**overrides: Any) -> PortfolioConfig:
    """Return a PortfolioConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "init_cash": 10_000.0,
        "fees": 0.001,
        "slippage": 0.0005,
        "gross_cap": 1.0,
        "net_cap": 1.0,
        "direction": "longonly",
        "short_borrow_rate": 0.005,
        "short_rebate_rate": 0.0,
        "margin_interest_rate": 0.0324,
        # Mechanics tests assert exact same-bar order dates/prices; pin same_close so they
        # stay shift-free. Production PortfolioConfig defaults to next_close; tests that
        # exercise realistic fills set fill_timing explicitly.
        "fill_timing": "same_close",
    }
    defaults.update(overrides)
    return PortfolioConfig(**defaults)


def make_report_config(**overrides: Any) -> ReportConfig:
    """Return a ReportConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "min_oos_sharpe": 0.5,
        "max_oos_drawdown": 0.35,
        "min_oos_trades": 5,
        "freq": "1D",
        "year_freq": "252D",
    }
    defaults.update(overrides)
    return ReportConfig(**defaults)


def make_run_source_ref_config(**overrides: Any) -> RunSourceRefConfig:
    """Return a RunSourceRefConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "id": "demo.strategy",
        "params": {},
    }
    defaults.update(overrides)
    return RunSourceRefConfig(**defaults)


def make_run_indicator_source_config(**overrides: Any) -> RunIndicatorSourceConfig:
    """Return a RunIndicatorSourceConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "id": "demo.indicator",
        "params": {},
    }
    defaults.update(overrides)
    return RunIndicatorSourceConfig(**defaults)


def make_ranking_config(**overrides: Any) -> RankingConfig:
    """Return a RankingConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "metric": "total_return",
        "min_weight": 0.3,
        "min_trades": 0,
    }
    defaults.update(overrides)
    return RankingConfig(**defaults)


def make_run_split_config(**overrides: Any) -> RunSplitConfig:
    """Return a RunSplitConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "method": "from_rolling",
        "params": {"length": 20, "split": 0.5},
        "max_splits": 100,
        "max_estimated_output_cells": 25_000_000,
        "max_public_artifact_bytes": 10_000_000,
    }
    defaults.update(overrides)
    return RunSplitConfig(**defaults)


def make_optimization_config(**overrides: Any) -> OptimizationConfig:
    """Return an OptimizationConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "search": "grid",
        "split": make_run_split_config(),
        "random_subset": None,
        "seed": None,
        "execute": {},
    }
    defaults.update(overrides)
    return OptimizationConfig(**defaults)


def make_lock(**overrides: Any) -> Lock:
    """Return a Lock with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "run_id": "run-a",
        "candidate_id": "best",
    }
    defaults.update(overrides)
    return Lock(**defaults)


def make_run_config(**overrides: Any) -> RunConfig:
    """Return a RunConfig with valid defaults, overridden by any kwargs.

    Nested section factories supply defaults for every section; callers pass
    ready-made instances for the sections they need to differ
    (e.g. ``portfolio=make_portfolio_config(fees=0)``).
    """
    defaults: dict[str, Any] = {
        "name": "test-run",
        "strategy": make_run_source_ref_config(),
        "indicators": [make_run_indicator_source_config()],
        "ranking": make_ranking_config(),
        "schema_version": CONFIG_SCHEMA_VERSION,
        "data": make_data_config(),
        "portfolio": make_portfolio_config(),
        "report": make_report_config(),
        "optimization": None,
        "lock": None,
        "output_dir": "runs",
    }
    defaults.update(overrides)
    return RunConfig(**defaults)


def make_candidate_grid(
    spec: Mapping[CandidateKey, Mapping[Any, Mapping[str, float | None]]],
    *,
    param_names: list[str] | None = None,
) -> CandidateGrid:
    """Build a CandidateGrid from a boundary-vocabulary spec.

    ``spec`` maps each CandidateKey to its per-Split per-Metric values. Scalar
    candidate keys are wrapped as 1-tuples automatically. ``None`` values are
    converted to NaN for the DataFrame spine so the grid's read surface can
    normalize them back to None.

    The factory constructs through ``from_sweep`` so every test grid exercises
    the production construction path.
    """
    if not spec:
        # Empty grid — still valid by construction; carries the default
        # param level and metric column the non-empty path would produce.
        if param_names is None:
            param_names = ["param"]
        index = pd.MultiIndex.from_tuples(
            [], names=[*param_names, SPLIT_LEVEL]
        )
        return CandidateGrid.from_sweep(
            pd.DataFrame({"sharpe": []}, index=index, dtype="float64")
        )

    # Collect all metric ids across all candidates and splits.
    metric_ids_set: set[str] = set()
    for per_split in spec.values():
        for per_metric in per_split.values():
            metric_ids_set.update(per_metric.keys())
    metric_ids = sorted(metric_ids_set)

    # Derive param names from the first candidate key if not provided.
    if param_names is None:
        first_key = next(iter(spec))
        if isinstance(first_key, tuple):
            n = len(first_key)
            param_names = [f"param_{i}" for i in range(n)] if n > 1 else ["param"]
        else:
            param_names = ["param"]

    # Build MultiIndex rows.
    tuples: list[tuple] = []
    rows: list[dict[str, float]] = []
    for key, per_split in spec.items():
        key_tuple = (key,) if not isinstance(key, tuple) else key
        for split_label, per_metric in per_split.items():
            tuples.append((*key_tuple, split_label))
            rows.append({
                mid: (np.nan if v is None else float(v))
                for mid, v in per_metric.items()
            })
    index = pd.MultiIndex.from_tuples(tuples, names=[*param_names, SPLIT_LEVEL])
    # Fill missing metric columns with NaN.
    frame = pd.DataFrame(rows, index=index)
    for mid in metric_ids:
        if mid not in frame.columns:
            frame[mid] = np.nan
    frame = frame[metric_ids]
    return CandidateGrid.from_sweep(frame)


def make_component_registry(
    definitions: Mapping[
        ComponentFamily,
        Mapping[str, ComponentDefinition],
    ],
) -> FrozenComponentRegistry:
    """Build a FrozenComponentRegistry in memory — no tmp dirs, no file writing.

    Accepts fully-constructed ``ComponentDefinition`` objects keyed by family
    and id; families may be omitted.  Delegates to
    ``freeze_component_registry`` so the factory stops re-deriving the freeze
    loop and fingerprint recipe.
    """
    return freeze_component_registry(definitions)


def make_setup_result(**overrides: Any) -> SetupResult:
    """Return a SetupResult with valid defaults, overridden by any kwargs.

    All fields carry plausible no-op values so tests that only exercise a
    single field (or a subset) can construct the wrapper directly without
    reaching into the setup stage internals.
    """
    close = pd.DataFrame({0: [1.0, 2.0]})
    open_ = pd.DataFrame({0: [1.0, 2.0]})
    defaults: dict[str, Any] = {
        "store_path": Path("candidates.sqlite3"),
        "optimization_source": _fake_optimization_source(),
        "close": close,
        "open_": open_,
        "pnl_close": close,
        "pnl_open": open_,
        "split_result": _fake_split_result(),
    }
    defaults.update(overrides)
    return SetupResult(**defaults)


class _FakeOptimizationSource:
    def __init__(self) -> None:
        self.params: dict[str, Any] = {}
        self.evidence: dict[str, Any] = {"strategy": {}}


def _fake_optimization_source() -> Any:
    return _FakeOptimizationSource()


class _FakeSplitResult:
    def __init__(self) -> None:
        self.metadata: dict[str, int] = {"n_splits": 2}
        self.splits: list[Any] = []


def _fake_split_result() -> Any:
    return _FakeSplitResult()
