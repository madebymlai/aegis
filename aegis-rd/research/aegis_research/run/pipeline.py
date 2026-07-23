from __future__ import annotations

from typing import TYPE_CHECKING

from aegis_data.catalog import catalog_data_port

from research.aegis_research.candidates.derivation import derive_candidate_set
from research.aegis_research.candidates.models import CandidateSet
from research.aegis_research.candidates.store import CandidateStore
from research.aegis_research.component_registry import FrozenComponentRegistry
from research.aegis_research.configuration import ResolvedRunConfig, RunConfig
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.portfolio_simulation import ResolvedBook
from research.aegis_research.run._stages.execution import ExecutionResult, run_pipeline_execution
from research.aegis_research.run._stages.setup import SetupResult, run_pipeline_setup
from research.aegis_research.run.data import RunData, load_run_data
from research.aegis_research.run.data_contract import (
    build_run_data_array_contract,
)
from research.aegis_research.run.identity import RunId
from research.aegis_research.run.result import OptimizationSummary, RunResult

if TYPE_CHECKING:
    from aegis_data.custom_data import CustomDataProviderMap


def run_strategy_sweep(
    resolved_config: ResolvedRunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    run_id: str | None = None,
    custom_data_providers: CustomDataProviderMap | None = None,
) -> RunResult:
    """Execute one Run and atomically commit its representative Candidates."""
    config = resolved_config.config
    attempted_run_id = RunId.create(run_id, run_name=config.name)
    array_contract = build_run_data_array_contract(config, component_registry)
    array_contract.assert_configured()
    run_data = load_run_data(
        config.data,
        required_arrays=array_contract.required_arrays,
        port=catalog_data_port(
            config.data.path,
            resolver=config.data.marking_resolver(),
        ),
        custom_data_providers=custom_data_providers,
    )
    metric_registry = resolved_config.metric_registry
    setup, execution = _execute_run(
        config,
        component_registry=component_registry,
        run_data=run_data,
        metric_registry=metric_registry,
    )
    candidate_set = derive_candidate_set(
        run_id=attempted_run_id,
        config=config,
        setup=setup,
        execution=execution,
        array_contract=array_contract,
        metric_registry_fingerprint=metric_registry.fingerprint,
    )
    result = _build_run_result(
        config, setup=setup, execution=execution, candidate_set=candidate_set
    )
    with CandidateStore(setup.store_path) as candidate_store:
        candidate_store.commit_candidates(candidate_set)
    return result


def _execute_run(
    config: RunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    run_data: RunData,
    metric_registry: FrozenMetricRegistry,
) -> tuple[SetupResult, ExecutionResult]:
    setup = run_pipeline_setup(
        config=config,
        component_registry=component_registry,
        run_data=run_data,
    )
    execution = run_pipeline_execution(
        config=config,
        setup=setup,
        book=ResolvedBook.resolve(config.portfolio, run_data),
        metric_registry=metric_registry,
    )
    return setup, execution


def _build_run_result(
    config: RunConfig,
    *,
    setup: SetupResult,
    execution: ExecutionResult,
    candidate_set: CandidateSet,
) -> RunResult:
    result = execution.optimization_result
    summary = OptimizationSummary(
        ranking_metric=config.ranking.metric,
        observation_block_bars=execution.observation_block_bars,
        observation_block_count=execution.observation_block_count,
        candidate_count=len({row["candidate_key"] for row in candidate_set.candidates}),
        total=result.total_candidates,
        excluded_invalid=result.excluded_invalid,
        excluded_degenerate=result.excluded_degenerate,
    )
    return RunResult.create(
        run_id=candidate_set.run_id,
        candidate_store_path=setup.store_path,
        optimization=summary,
        candidates=candidate_set.candidates,
    )


__all__ = ["run_strategy_sweep"]
