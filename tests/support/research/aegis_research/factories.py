"""Test-construction factories for Run Config dataclasses.

Each factory supplies valid defaults for every field and accepts **overrides.
Routing construction through factories means porting one helper instead of N call
sites when section defaults change (e.g. when pydantic v2 adoption drops
gross_cap and data.arrays schema defaults).

These are test-support only — no production code changes.
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.config import (
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
        "source": "synthetic",
        "arrays": ["OHLCV"],
        "symbols": ["SYN"],
        "start": None,
        "end": None,
        "timeframe": "1D",
        "path": None,
        "seed": 42,
        "rows": 750,
        "missing_index": "raise",
        "missing_columns": "raise",
        "tz_localize": None,
        "tz_convert": None,
        "skip_on_error": False,
        "silence_warnings": False,
        "quality": make_data_quality_config(),
        "wrapper_kwargs": {},
        "provider_kwargs": {},
        "execution_kwargs": {},
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
