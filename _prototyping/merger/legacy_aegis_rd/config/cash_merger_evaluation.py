"""Paired whole-book evaluation for the Demeter fixed-cash merger family."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.configuration import load_run_config
from research.aegis_research.data import load_market_data_result, prepare_run_arrays
from research.aegis_research.floor_evaluation import (
    FloorEvaluationSettings,
    evaluate_floor_pair,
    load_locked_strategy_returns,
)
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
from research.aegis_research.optimization.portfolio_simulation import ResolvedBook
from research.aegis_research.optimization.portfolio_simulation._simulation import (
    simulate_portfolio_batch,
)


class CashMergerEvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class CashMergerSimulation:
    config_path: str
    config_name: str
    base_currency: str
    returns: pd.Series
    diagnostics: dict[str, Any]


def evaluate_cash_merger_frontier(
    trend_config: str | Path,
    merger_configs: Mapping[str, str | Path],
    *,
    baseline_label: str = "12",
    residual_label: str = "residual_12",
    settings: FloorEvaluationSettings | None = None,
) -> dict[str, Any]:
    """Compare every locked merger config beside locked Atalanta on common history."""

    trend = load_locked_strategy_returns(trend_config)
    simulations = {
        label: load_locked_cash_merger_simulation(path)
        for label, path in merger_configs.items()
    }
    reports = {}
    for label, simulation in simulations.items():
        if simulation.base_currency != trend.base_currency:
            raise CashMergerEvaluationError(
                f"{label} base currency {simulation.base_currency!r} differs from "
                f"Atalanta {trend.base_currency!r}"
            )
        trend_monthly, merger_monthly = _common_monthly(
            trend.returns, simulation.returns
        )
        reports[label] = {
            "whole_book": evaluate_floor_pair(
                trend_monthly, merger_monthly, settings=settings
            ),
            "demeter": simulation.diagnostics,
            "config": {
                "path": simulation.config_path,
                "name": simulation.config_name,
            },
        }

    residual_effect = None
    if baseline_label in simulations and residual_label in simulations:
        residual_effect = _residual_effect(
            simulations[baseline_label],
            simulations[residual_label],
            reports[baseline_label],
            reports[residual_label],
        )
    return {
        "schema_version": "cash_merger_frontier.v1",
        "trend_config": trend.evidence(),
        "frontier": reports,
        "residual_entry_effect": residual_effect,
    }


def load_locked_cash_merger_simulation(config_path: str | Path) -> CashMergerSimulation:
    """Reproduce one locked Demeter config through its native whole-unit simulator."""

    path = Path(config_path).expanduser().resolve()
    resolved = load_run_config(path)
    config = resolved.config
    if config.strategy.id != "demeter.cash_merger_break_risk":
        raise CashMergerEvaluationError(
            f"config {path} does not use demeter.cash_merger_break_risk"
        )
    if config.lock is None:
        raise CashMergerEvaluationError(
            f"config {path} must lock a Candidate before paired evaluation"
        )
    registry = resolved.component_registry
    if registry is None:
        raise CashMergerEvaluationError(f"config {path} has no Component registry")

    array_contract = build_run_data_array_contract(config, registry)
    data_result = load_market_data_result(
        config.data, required_arrays=array_contract.required_arrays
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
    fixed_params = {FIXED_CANDIDATE_PARAM: [0]}
    close = arrays.signal.array("Close")
    precomputed = source.precompute(close, 1, **fixed_params)
    indicators = precomputed.window(slice(None), [(0,)])
    allocations = source.simulate(close, indicators, 1, **fixed_params)
    book = ResolvedBook.resolve(
        config,
        arrays.currency_conversion,
        arrays.size_increment_by_instrument,
    )
    portfolio = simulate_portfolio_batch(
        arrays.pnl_close,
        allocations,
        book,
        open_=arrays.pnl_open,
        market_index=close.index,
        periods_per_year=config.report.periods_per_year,
        distributions=arrays.distributions,
        currency_conversion=arrays.currency_conversion,
    )
    value = portfolio.get_value()
    value_series = value if isinstance(value, pd.Series) else value.iloc[:, 0]
    returns = value_series.pct_change(fill_method=None).iloc[1:]
    status = pd.DataFrame(
        indicators["deal_status"], index=close.index, columns=close.columns
    )
    diagnostics = summarize_cash_merger_execution(
        close=arrays.pnl_close,
        target_weights=_single_candidate_frame(allocations, close.columns),
        deal_status=status,
        assets=_single_candidate_frame(portfolio.assets, close.columns),
        portfolio_value=value_series,
        order_fees=float(np.asarray(portfolio.orders.fees.sum()).sum()),
        size_increments=arrays.size_increment_by_instrument,
    )
    return CashMergerSimulation(
        config_path=str(path),
        config_name=config.name,
        base_currency=config.portfolio.base_currency,
        returns=returns.rename(config.name),
        diagnostics=diagnostics,
    )


def summarize_cash_merger_execution(
    *,
    close: pd.DataFrame,
    target_weights: pd.DataFrame,
    deal_status: pd.DataFrame,
    assets: pd.DataFrame,
    portfolio_value: pd.Series,
    order_fees: float,
    size_increments: Mapping[Any, float],
) -> dict[str, Any]:
    """Report concentration, actual costs, whole-unit compliance, and deal breaks."""

    active = target_weights.abs() > 1e-12
    gross = target_weights.abs().sum(axis=1)
    normalized = target_weights.abs().div(gross.replace(0.0, np.nan), axis=0)
    effective_positions = 1.0 / normalized.pow(2).sum(axis=1)
    target_fraction = gross.clip(upper=1.0)
    realized_notional = assets.abs().mul(close.abs()).sum(axis=1, min_count=1)
    realized_fraction = realized_notional.div(portfolio_value.abs()).replace(
        [np.inf, -np.inf], np.nan
    )
    unexpressed_target = (target_fraction - realized_fraction).clip(lower=0.0)
    increment = pd.Series(size_increments).reindex(assets.columns)
    if increment.isna().any():
        missing = [str(column) for column in increment.index[increment.isna()]]
        raise CashMergerEvaluationError(
            f"execution diagnostics lack size increments for {missing}"
        )
    scaled_assets = assets.div(increment, axis=1)
    whole_unit_compliant = bool(
        np.isclose(scaled_assets.to_numpy(), np.round(scaled_assets.to_numpy()), atol=1e-9).all()
    )
    resolutions = _resolution_contributions(
        close, deal_status, assets, portfolio_value
    )
    return {
        "concentration": {
            "maximum_target_weight": float(target_weights.abs().to_numpy().max()),
            "maximum_active_positions": int(active.sum(axis=1).max()),
            "mean_active_positions": float(active.sum(axis=1).mean()),
            "mean_effective_positions": float(effective_positions.dropna().mean())
            if effective_positions.notna().any()
            else 0.0,
            "mean_cash_target": float((1.0 - gross.clip(upper=1.0)).mean()),
        },
        "deployment": {
            "mean_target_fraction": float(target_fraction.mean()),
            "mean_realized_fraction": float(realized_fraction.dropna().mean()),
            "mean_unexpressed_target_fraction": float(
                unexpressed_target.dropna().mean()
            ),
        },
        "costs": {"realized_order_fees": order_fees},
        "execution": {
            "fractional_execution_used": not whole_unit_compliant,
            "size_increment_compliant": whole_unit_compliant,
            "minimum_portfolio_value": float(portfolio_value.min()),
        },
        "resolution_attribution": resolutions,
    }


def _resolution_contributions(
    close: pd.DataFrame,
    status: pd.DataFrame,
    assets: pd.DataFrame,
    value: pd.Series,
) -> dict[str, Any]:
    rows = []
    previous_status = status.shift(1).fillna(0.0)
    for row in range(1, len(close)):
        for column in close.columns:
            current = status.iloc[row][column]
            if current not in (-1.0, 2.0) or previous_status.iloc[row][column] == current:
                continue
            previous_quantity = float(assets.iloc[row - 1][column])
            contribution = (
                previous_quantity
                * (float(close.iloc[row][column]) - float(close.iloc[row - 1][column]))
                / float(value.iloc[row - 1])
            )
            rows.append(
                {
                    "date": close.index[row].date().isoformat(),
                    "symbol": str(column),
                    "outcome": "terminated" if current == -1.0 else "completed",
                    "portfolio_contribution": contribution,
                }
            )
    terminated = [row["portfolio_contribution"] for row in rows if row["outcome"] == "terminated"]
    completed = [row["portfolio_contribution"] for row in rows if row["outcome"] == "completed"]
    return {
        "events": rows,
        "terminated_contribution": float(sum(terminated)),
        "completed_contribution": float(sum(completed)),
    }


def _single_candidate_frame(frame: pd.DataFrame, columns: pd.Index) -> pd.DataFrame:
    return pd.DataFrame(frame.to_numpy(), index=frame.index, columns=columns)


def _common_monthly(
    left: pd.Series, right: pd.Series
) -> tuple[pd.Series, pd.Series]:
    common = left.index.intersection(right.index)
    if common.empty:
        raise CashMergerEvaluationError("Atalanta and Demeter have no common history")
    monthly = pd.concat(
        [
            _complete_monthly_returns(left.reindex(common)),
            _complete_monthly_returns(right.reindex(common)),
        ],
        axis=1,
    ).dropna()
    if monthly.empty:
        raise CashMergerEvaluationError(
            "Atalanta and Demeter have no common complete months"
        )
    return monthly.iloc[:, 0], monthly.iloc[:, 1]


def _complete_monthly_returns(returns: pd.Series) -> pd.Series:
    monthly = (1.0 + returns).resample("ME").prod() - 1.0
    first_observation = returns.index.min()
    first_month_start = first_observation.to_period("M").start_time
    if first_observation > first_month_start + pd.Timedelta(days=7):
        monthly = monthly.iloc[1:]
    last_observation = returns.index.max()
    last_month_end = last_observation.to_period("M").end_time.normalize()
    if last_observation < last_month_end - pd.Timedelta(days=3):
        monthly = monthly.iloc[:-1]
    return monthly


def _residual_effect(
    baseline: CashMergerSimulation,
    residual: CashMergerSimulation,
    baseline_report: Mapping[str, Any],
    residual_report: Mapping[str, Any],
) -> dict[str, Any]:
    common = baseline.returns.index.intersection(residual.returns.index)
    delta = residual.returns.reindex(common) - baseline.returns.reindex(common)
    baseline_ce = baseline_report["whole_book"]["comparison"]["delta"][
        "mppm_certainty_equivalent"
    ]
    residual_ce = residual_report["whole_book"]["comparison"]["delta"][
        "mppm_certainty_equivalent"
    ]
    return {
        "annualized_incremental_return": float(delta.mean() * 252.0),
        "whole_book_mppm_delta_change": float(residual_ce - baseline_ce),
        "realized_order_fee_change": float(
            residual.diagnostics["costs"]["realized_order_fees"]
            - baseline.diagnostics["costs"]["realized_order_fees"]
        ),
    }


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]
