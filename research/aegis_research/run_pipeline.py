from __future__ import annotations

from collections.abc import Callable
from typing import Any

from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
)
from research.aegis_research.configuration import (
    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
    ConfigValidationError,
    ConfigValidationIssue,
    ResolvedRunConfig,
    RunConfig,
)
from research.aegis_research.data import (
    MarketDataBundle,
    MarketDataResult,
    load_market_data_result,
    market_data_bundle,
)
from research.aegis_research.data_arrays import (
    DataArrayContract,
    with_data_array_contract_metadata,
)
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.completion import (
    build_run_refs,
    run_pipeline_completion,
)
from research.aegis_research.optimization.pipeline.execution import run_pipeline_execution
from research.aegis_research.optimization.pipeline.publishing import run_pipeline_publishing
from research.aegis_research.optimization.pipeline.setup import run_pipeline_setup
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_array_contract,
)
from research.aegis_research.provenance.data_artifacts import write_data_metadata_artifact
from research.aegis_research.provenance.recorder import RerunMode, RunRecorder
from research.aegis_research.provenance.run_store import RunStore


def run_strategy_sweep(
    resolved_config: ResolvedRunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    rerun_mode: str = RerunMode.NEW,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    supersedes_run_id: str | None = None,
    on_run_started: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    config = resolved_config.config
    if config.optimization is None:
        raise ConfigValidationError(
            [
                ConfigValidationIssue(
                    "optimization",
                    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
                )
            ]
        )
    array_contract = build_run_data_array_contract(config, component_registry)

    recorder = RunStore(config.output_dir).start_run(
        run_label=config.name,
        config=resolved_config.resolved_config_document(),
        mode=rerun_mode,
        run_id=run_id,
        parent_run_id=parent_run_id,
        supersedes_run_id=supersedes_run_id,
    )
    run_evidence = RunEvidence(
        recorder.manifest.evidence,
        component_registry_fingerprint=component_registry.fingerprint,
        data_arrays=array_contract.metadata(),
        optimization={},
        persist=recorder.persist,
    )
    recorder.persist()

    try:
        if on_run_started is not None:
            on_run_started(build_run_refs(recorder))
        array_contract.assert_configured()
        data_result = load_market_data_result(
            config.data,
            required_features=array_contract.required_arrays,
        )
        data_result = with_data_array_contract_metadata(data_result, array_contract)
        write_data_metadata_artifact(recorder, data_result)
        data_result.assert_usable()
        data_bundle = market_data_bundle(data_result)
        metric_registry = resolved_config.metric_registry
        return _run_optimization_strategy_sweep(
            config,
            component_registry=component_registry,
            recorder=recorder,
            data_result=data_result,
            data=data_bundle,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry.fingerprint,
            metric_registry=metric_registry,
            run_evidence=run_evidence,
        )
    except KeyboardInterrupt:
        recorder.mark_run_interrupted(
            diagnostic={"error_type": "KeyboardInterrupt", "message": "interrupted"}
        )
        raise
    except ConfigValidationError as error:
        recorder.mark_run_failed(diagnostic=_failure_diagnostic(error))
        raise
    except Exception as error:
        recorder.mark_run_failed(diagnostic=_failure_diagnostic(error))
        raise


def _failure_diagnostic(error: Exception) -> dict[str, str]:
    return {
        "error_type": type(error).__name__,
        "message": str(error)[:1000],
    }


def _run_optimization_strategy_sweep(
    config: RunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    recorder: RunRecorder,
    data_result: MarketDataResult,
    data: MarketDataBundle,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    metric_registry: FrozenMetricRegistry,
    run_evidence: RunEvidence,
) -> dict[str, Any]:
    # Stage 1: Setup — resolve locks, build optimization source and evidence baseline
    try:
        setup = run_pipeline_setup(
            config=config,
            component_registry=component_registry,
            data=data,
            data_result=data_result,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry_fingerprint,
            run_evidence=run_evidence,
        )
    except Exception as error:
        run_evidence.fail(EvidenceFailureStage.SETUP, error)
        raise

    # Stage 2: Execution — preflight gate, two-phase optimization sweep
    execution = run_pipeline_execution(
        config=config,
        setup=setup,
        metric_registry=metric_registry,
        run_evidence=run_evidence,
    )

    # Stage 3: Publishing — three representative candidates, candidate store
    publishing = run_pipeline_publishing(
        config=config,
        recorder=recorder,
        data_result=data_result,
        array_contract=array_contract,
        optimization_source=setup.optimization_source,
        execution=execution,
        run_evidence=run_evidence,
        store_path=setup.store_path,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )

    # Stage 4: Completion — artifact, completion, activation, result
    return run_pipeline_completion(
        setup=setup,
        publishing=publishing,
        config=config,
        recorder=recorder,
        data_result=data_result,
        array_contract=array_contract,
        run_evidence=run_evidence,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )

