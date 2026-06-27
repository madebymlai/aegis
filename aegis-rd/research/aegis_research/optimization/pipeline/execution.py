"""Pipeline execution stage.

Runs the preflight gate, executes the two-phase optimization, and records the
three-candidate result evidence for downstream stages.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.configuration import (
    RunConfig,
)
from research.aegis_research.market_data.currency import CurrencyConversion
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.candidate_evidence import result_evidence
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    EvidenceSection,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.setup import SetupResult
from research.aegis_research.optimization.preflight import (
    PreflightError,
    build_preflight,
)
from research.aegis_research.optimization.ranking import OptimizationResult
from research.aegis_research.optimization.runner import execute_optimization
from research.aegis_research.optimization.source import (
    OptimizationSourceError,
)
from research.aegis_research.portfolios import fx_adjusted_fees


@dataclass(frozen=True)
class ExecutionResult:
    """Typed hand-off from the pipeline execution stage."""

    optimization_result: OptimizationResult


def _fx_fees(config: RunConfig, currency_conversion: CurrencyConversion | None) -> pd.Series:
    """Per-instrument trade fees for the book.

    ``fx_adjusted_fees`` is the single fee builder: it returns the base fee for
    every leg and adds the FX surcharge only to non-base legs, so a zero-cost or
    single-currency book gets a uniform no-op series - no branch, no special case.
    A leg is non-base by its currency *derived from the resolved Instrument* (the
    conversion's ``currency_by_instrument_id``), never a configured field; a
    single-currency book has no conversion, so every leg reads as base.
    """
    portfolio = config.portfolio
    instrument_ids = tuple(InstrumentId.from_str(value) for value in config.data.instruments)
    currency_by_instrument_id = (
        currency_conversion.currency_by_instrument_id
        if currency_conversion is not None
        else dict.fromkeys(instrument_ids, portfolio.base_currency)
    )
    return fx_adjusted_fees(
        instrument_ids,
        currency_by_instrument_id,
        portfolio.base_currency,
        base_fee=portfolio.fees,
        fx_conversion_cost=portfolio.fx_conversion_cost,
    )


def run_pipeline_execution(
    *,
    config: RunConfig,
    setup: SetupResult,
    metric_registry: FrozenMetricRegistry,
    run_evidence: RunEvidence,
    currency_conversion: CurrencyConversion | None = None,
) -> ExecutionResult:
    """Execute the preflight gate and two-phase optimization sweep."""
    # The public entry point rejects runs without an optimization block, so by the
    # time execution runs the optimization config is guaranteed present.
    assert config.optimization is not None
    try:
        preflight = build_preflight(
            params=setup.optimization_source.params,
            optimization=config.optimization,
            splits=setup.split_result.splits,
            symbol_count=len(setup.close.columns),
            has_open_prices=True,
        )
        run_evidence.record(EvidenceSection.PREFLIGHT, preflight)
    except PreflightError as error:
        run_evidence.record(EvidenceSection.PREFLIGHT, error.diagnostics)
        run_evidence.fail(EvidenceFailureStage.PREFLIGHT, error)
        raise OptimizationSourceError(str(error)) from error

    try:
        optimization_result = execute_optimization(
            close=setup.close,
            open_=setup.open_,
            pnl_close=setup.pnl_close,
            pnl_open=setup.pnl_open,
            source=setup.optimization_source,
            optimization=config.optimization,
            portfolio=config.portfolio,
            report=config.report,
            ranking=config.ranking,
            metric_registry=metric_registry,
            split_result=setup.split_result,
            fees_by_symbol=_fx_fees(config, currency_conversion),
        )
    except Exception as error:
        run_evidence.fail(EvidenceFailureStage.EXECUTION, error)
        raise

    run_evidence.record(EvidenceSection.EXECUTION, result_evidence(optimization_result))

    return ExecutionResult(optimization_result=optimization_result)
