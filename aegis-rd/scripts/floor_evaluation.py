"""Paired evaluation of two locked strategy configs as the floor book.

The module owns two related contracts:

* reproduce each locked config through the production market-data, Component,
  allocation, and portfolio-simulation path; and
* compare the pre-declared trend/carry mix with trend alone on their common
  monthly history using whole-book utility and dependence-aware diagnostics.

It deliberately does not select Candidates. A config without a top-level Lock
is an experiment, not a strategy specification, and is rejected before data is
loaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.configuration import load_run_config
from research.aegis_research.data import load_market_data_result, prepare_run_arrays
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.candidate_store_identity import (
    candidate_store_path,
)
from research.aegis_research.optimization.component_source import (
    build_component_optimization_source,
)
from research.aegis_research.optimization.lock_run import resolve_lock_run
from research.aegis_research.optimization.param_namespace import FIXED_CANDIDATE_PARAM
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_array_contract,
)
from research.aegis_research.optimization.window_evaluation import (
    ResolvedBook,
    WindowEvaluator,
)

MONTHS_PER_YEAR = 12.0


class FloorEvaluationError(ValueError):
    """A locked floor-pair evaluation cannot be constructed as declared."""


@dataclass(frozen=True)
class FloorEvaluationSettings:
    """Pre-declared floor comparison and resampling policy."""

    carry_weight: float = 0.40
    risk_aversion: float = 3.0
    bootstrap_samples: int = 2_000
    block_lengths: tuple[int, ...] = (1, 3, 6)
    seed: int = 42

    def __post_init__(self) -> None:
        if not 0.0 <= self.carry_weight <= 1.0:
            raise ValueError("carry_weight must be between zero and one")
        if self.risk_aversion <= 0.0:
            raise ValueError("risk_aversion must be positive")
        if self.bootstrap_samples < 1:
            raise ValueError("bootstrap_samples must be positive")
        if not self.block_lengths or any(length < 1 for length in self.block_lengths):
            raise ValueError("block_lengths must contain positive integers")


@dataclass(frozen=True)
class LockedStrategyReturns:
    """One locked config's production-simulated net return stream."""

    config_path: str
    config_hash: str
    config_name: str
    base_currency: str
    lock_run_id: str
    lock_candidate_id: str
    resolved_candidate_key: str
    returns: pd.Series

    def evidence(self) -> dict[str, Any]:
        return {
            "config_path": self.config_path,
            "config_hash": self.config_hash,
            "config_name": self.config_name,
            "base_currency": self.base_currency,
            "lock_run_id": self.lock_run_id,
            "lock_candidate_id": self.lock_candidate_id,
            "resolved_candidate_key": self.resolved_candidate_key,
            "observations": len(self.returns),
            "start": self.returns.index.min().date().isoformat(),
            "end": self.returns.index.max().date().isoformat(),
        }


def load_locked_strategy_returns(config_path: str | Path) -> LockedStrategyReturns:
    """Reproduce one locked config and return its full net daily return stream."""
    path = Path(config_path).expanduser().resolve()
    resolved = load_run_config(path)
    config = resolved.config
    if config.lock is None:
        raise FloorEvaluationError(
            f"config {path} has no top-level lock; select and lock a Candidate before "
            "paired evaluation"
        )
    registry = resolved.component_registry
    if registry is None:
        raise FloorEvaluationError(f"config {path} has no resolved Component registry")

    array_contract = build_run_data_array_contract(config, registry)
    array_contract.assert_configured()
    data_result = load_market_data_result(
        config.data,
        required_arrays=array_contract.required_arrays,
    )
    arrays = prepare_run_arrays(data_result)

    store_path = candidate_store_path(config)
    if not store_path.is_absolute():
        store_path = _repository_root() / store_path
    with CandidateStore(store_path) as candidate_store:
        lock_run = resolve_lock_run(config.lock, store=candidate_store)

    source = build_component_optimization_source(
        config,
        component_registry=registry,
        data=arrays.signal,
        resolved_component_params=lock_run.component_params,
        force_locked=True,
    )
    if tuple(source.params) != (FIXED_CANDIDATE_PARAM,):
        raise FloorEvaluationError(
            f"locked config {path} still exposes Candidate axes: {list(source.params)}"
        )
    fixed_params = {FIXED_CANDIDATE_PARAM: [0]}
    close = arrays.signal.array("Close")
    precomputed = source.precompute(close, 1, **fixed_params)
    evaluator = WindowEvaluator(
        source=source,
        book=ResolvedBook.resolve(
            config,
            data_result.currency_conversion,
            data_result.size_increment_by_instrument,
        ),
        report=config.report,
        arrays=arrays,
        store=precomputed,
        extractors={},
    )
    return_frame = evaluator.portfolio_returns(slice(None), **fixed_params)
    if return_frame.shape[1] != 1:
        raise FloorEvaluationError(
            f"locked config {path} produced {return_frame.shape[1]} return streams; expected one"
        )
    returns = return_frame.iloc[:, 0].dropna().rename(config.name)
    returns.index = pd.DatetimeIndex(returns.index).tz_localize(None).normalize()
    if returns.empty:
        raise FloorEvaluationError(f"locked config {path} produced no returns")

    return LockedStrategyReturns(
        config_path=str(path),
        config_hash=resolved.raw_config_hash,
        config_name=config.name,
        base_currency=config.portfolio.base_currency,
        lock_run_id=config.lock.run_id,
        lock_candidate_id=config.lock.candidate_id,
        resolved_candidate_key=lock_run.candidate_key,
        returns=returns,
    )


def evaluate_locked_floor_configs(
    trend_config: str | Path,
    carry_config: str | Path,
    *,
    settings: FloorEvaluationSettings | None = None,
) -> dict[str, Any]:
    """Run two locked configs and evaluate their common realized floor history."""
    trend = load_locked_strategy_returns(trend_config)
    carry = load_locked_strategy_returns(carry_config)
    if trend.base_currency != carry.base_currency:
        raise FloorEvaluationError(
            "trend and carry configs must use the same portfolio base currency; "
            f"got {trend.base_currency!r} and {carry.base_currency!r}"
        )

    common_daily = trend.returns.index.intersection(carry.returns.index)
    if common_daily.empty:
        raise FloorEvaluationError("trend and carry configs have no common daily history")
    trend_monthly = _complete_monthly_returns(trend.returns.reindex(common_daily))
    carry_monthly = _complete_monthly_returns(carry.returns.reindex(common_daily))
    report = evaluate_floor_pair(trend_monthly, carry_monthly, settings=settings)
    report["configs"] = {"trend": trend.evidence(), "carry": carry.evidence()}
    report["evidence_status"] = {
        "classification": "descriptive_reused_history",
        "fresh_out_of_sample": False,
        "reason": (
            "both Candidates were selected before this paired comparison; confidence intervals "
            "describe the reused common history and are not a fresh promotion test"
        ),
    }
    return report


def evaluate_floor_pair(
    trend_returns: pd.Series,
    carry_returns: pd.Series,
    *,
    settings: FloorEvaluationSettings | None = None,
) -> dict[str, Any]:
    """Compare a pre-declared trend/carry mix with trend alone.

    Inputs are periodic net returns from the two strategy configs. The function
    aligns observations pairwise and never rescales either leg from full-sample
    volatility. The mix therefore preserves the pre-declared 60/40 evaluation
    weight instead of manufacturing a hindsight-matched pair.
    """
    policy = settings or FloorEvaluationSettings()
    paired = pd.concat(
        [trend_returns.rename("trend"), carry_returns.rename("carry")], axis=1, join="inner"
    ).dropna()
    if paired.empty:
        raise ValueError("trend and carry returns have no common observations")
    if len(paired) < 12:
        raise ValueError("trend and carry returns need at least 12 common observations")
    if (paired <= -1.0).any(axis=None):
        raise ValueError("periodic returns must be greater than -100%")

    weight = policy.carry_weight
    trend = paired["trend"].to_numpy(dtype=float)
    carry = paired["carry"].to_numpy(dtype=float)
    composite = (1.0 - weight) * trend + weight * carry
    comparison = {
        "trend_only": _performance_summary(trend, policy.risk_aversion),
        "composite": _performance_summary(composite, policy.risk_aversion),
    }
    comparison["delta"] = _performance_delta(
        comparison["composite"], comparison["trend_only"]
    )

    return {
        "schema_version": "floor_pair_evaluation.v1",
        "periodicity": "monthly",
        "common_history": {
            "start": paired.index.min().date().isoformat(),
            "end": paired.index.max().date().isoformat(),
            "observations": len(paired),
        },
        "allocation": {
            "model": "fixed_monthly_return_mix",
            "trend_weight": 1.0 - weight,
            "carry_weight": weight,
            "leg_volatility_normalization": False,
            "live_trader_allocator_replay": False,
        },
        "comparison": comparison,
        "dependence": _dependence_summary(trend, carry),
        "bootstrap": _bootstrap_sensitivity(trend, carry, policy),
    }


def _monthly_returns(returns: pd.Series) -> pd.Series:
    return (1.0 + returns).resample("ME").prod() - 1.0


def _complete_monthly_returns(returns: pd.Series) -> pd.Series:
    monthly = _monthly_returns(returns)
    first_observation = returns.index.min()
    first_month_start = first_observation.to_period("M").start_time
    if first_observation > first_month_start + pd.Timedelta(days=7):
        monthly = monthly.iloc[1:]
    last_observation = returns.index.max()
    last_month_end = last_observation.to_period("M").end_time.normalize()
    if last_observation < last_month_end - pd.Timedelta(days=3):
        monthly = monthly.iloc[:-1]
    return monthly


def _performance_summary(returns: np.ndarray, risk_aversion: float) -> dict[str, float]:
    equity = np.cumprod(1.0 + returns)
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    volatility = float(np.std(returns, ddof=1) * np.sqrt(MONTHS_PER_YEAR))
    return {
        "monthly_mean": float(np.mean(returns)),
        "annualized_return": float(equity[-1] ** (MONTHS_PER_YEAR / len(returns)) - 1.0),
        "annualized_volatility": volatility,
        "sharpe": _sharpe(returns),
        "mppm_certainty_equivalent": _mppm(returns, risk_aversion),
        "max_drawdown": float(np.min(drawdown)),
        "skew": float(pd.Series(returns).skew()),
        "worst_month": float(np.min(returns)),
    }


def _performance_delta(
    composite: dict[str, float], trend_only: dict[str, float]
) -> dict[str, float]:
    return {
        key: composite[key] - trend_only[key]
        for key in (
            "annualized_return",
            "annualized_volatility",
            "sharpe",
            "mppm_certainty_equivalent",
            "max_drawdown",
            "skew",
            "worst_month",
        )
    }


def _mppm(returns: np.ndarray, risk_aversion: float) -> float:
    growth = 1.0 + returns
    if risk_aversion == 1.0:
        return float(MONTHS_PER_YEAR * np.mean(np.log(growth)))
    power_mean = np.mean(growth ** (1.0 - risk_aversion))
    return float(MONTHS_PER_YEAR / (1.0 - risk_aversion) * np.log(power_mean))


def _sharpe(returns: np.ndarray) -> float:
    volatility = float(np.std(returns, ddof=1))
    if volatility == 0.0:
        return 0.0
    return float(np.mean(returns) / volatility * np.sqrt(MONTHS_PER_YEAR))


def _dependence_summary(trend: np.ndarray, carry: np.ndarray) -> dict[str, float | None]:
    threshold = float(np.quantile(trend, 0.10))
    downside = trend <= threshold
    return {
        "full_sample_correlation": _correlation(trend, carry),
        "trend_worst_decile_threshold": threshold,
        "trend_worst_decile_observations": int(np.sum(downside)),
        "trend_worst_decile_correlation": _correlation(trend[downside], carry[downside]),
        "carry_mean_in_trend_worst_decile": float(np.mean(carry[downside])),
    }


def _correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 2 or np.std(left) == 0.0 or np.std(right) == 0.0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _bootstrap_sensitivity(
    trend: np.ndarray,
    carry: np.ndarray,
    settings: FloorEvaluationSettings,
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(settings.seed)
    rows: list[dict[str, Any]] = []
    for block_length in settings.block_lengths:
        if block_length > len(trend):
            raise ValueError(
                f"block length {block_length} exceeds {len(trend)} common observations"
            )
        ce_deltas = np.empty(settings.bootstrap_samples)
        sharpe_deltas = np.empty(settings.bootstrap_samples)
        for sample_index in range(settings.bootstrap_samples):
            positions = _circular_block_positions(len(trend), block_length, rng)
            sampled_trend = trend[positions]
            sampled_carry = carry[positions]
            sampled_composite = (
                (1.0 - settings.carry_weight) * sampled_trend
                + settings.carry_weight * sampled_carry
            )
            ce_deltas[sample_index] = _mppm(
                sampled_composite, settings.risk_aversion
            ) - _mppm(sampled_trend, settings.risk_aversion)
            sharpe_deltas[sample_index] = _sharpe(sampled_composite) - _sharpe(
                sampled_trend
            )
        rows.append(
            {
                "block_length_months": block_length,
                "samples": settings.bootstrap_samples,
                "mppm_delta_interval_95": _percentile_interval(ce_deltas),
                "sharpe_delta_interval_95": _percentile_interval(sharpe_deltas),
            }
        )
    return rows


def _circular_block_positions(
    observations: int, block_length: int, rng: np.random.Generator
) -> np.ndarray:
    block_count = int(np.ceil(observations / block_length))
    starts = rng.integers(0, observations, size=block_count)
    offsets = np.arange(block_length)
    return ((starts[:, None] + offsets) % observations).ravel()[:observations]


def _percentile_interval(values: np.ndarray) -> list[float]:
    lower, upper = np.quantile(values, [0.025, 0.975])
    return [float(lower), float(upper)]


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]
