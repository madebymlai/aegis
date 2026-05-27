from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
)
from research.aegis_research.config import (
    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
    ConfigValidationError,
    ConfigValidationIssue,
    ResolvedRunConfig,
    RunConfig,
    known_config_secret_values,
    redact_text,
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
from research.aegis_research.optimization.pipeline_setup import run_pipeline_setup
from research.aegis_research.optimization.pipeline_execution import run_pipeline_execution
from research.aegis_research.optimization.pipeline_publishing import run_pipeline_publishing
from research.aegis_research.optimization.pipeline_completion import (
    build_run_refs,
    run_pipeline_completion,
)
from research.aegis_research.optimization.candidate_publishing import (
    candidate_store_namespace,
)
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_array_contract,
)
from research.aegis_research.provenance.experiment_artifacts import ExperimentArtifactWriter
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
        config=resolved_config.redacted_resolved_config(),
        mode=rerun_mode,
        run_id=run_id,
        parent_run_id=parent_run_id,
        supersedes_run_id=supersedes_run_id,
    )
    recorder.manifest.evidence = {
        "component_registry_fingerprint": component_registry.fingerprint,
        "data_arrays": array_contract.metadata(),
    }
    recorder.persist()
    known_secrets = known_config_secret_values(resolved_config.authored_config)

    try:
        if on_run_started is not None:
            on_run_started(build_run_refs(recorder))
        array_contract.assert_configured()
        data_result = load_market_data_result(
            config.data,
            required_features=array_contract.required_arrays,
        )
        data_result = with_data_array_contract_metadata(data_result, array_contract)
        ExperimentArtifactWriter(recorder).write_data_metadata_artifact(data_result)
        data_result.assert_usable()
        data_bundle = market_data_bundle(data_result)
        open_prices = data_bundle.feature("Open")
        return _run_optimization_strategy_sweep(
            config,
            component_registry=component_registry,
            recorder=recorder,
            data_result=data_result,
            data=data_bundle,
            open_prices=open_prices,
            array_contract=array_contract,
            metric_registry_fingerprint=(
                resolved_config.metric_registry.fingerprint
                if resolved_config.metric_registry
                else None
            ),
        )
    except KeyboardInterrupt:
        recorder.mark_run_interrupted(
            diagnostic={"error_type": "KeyboardInterrupt", "message": "interrupted"}
        )
        raise
    except ConfigValidationError as error:
        recorder.mark_run_failed(diagnostic=_failure_diagnostic(error, known_secrets=known_secrets))
        raise
    except Exception as error:
        recorder.mark_run_failed(diagnostic=_failure_diagnostic(error, known_secrets=known_secrets))
        raise


def _failure_diagnostic(error: Exception, *, known_secrets: tuple[str, ...]) -> dict[str, str]:
    return {
        "error_type": type(error).__name__,
        "message": redact_text(str(error), known_secrets)[:1000],
    }


def _run_optimization_strategy_sweep(
    config: RunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    recorder: RunRecorder,
    data_result: MarketDataResult,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    # Stage 1: Setup — resolve locks, build optimization source and evidence baseline
    setup = run_pipeline_setup(
        config=config,
        component_registry=component_registry,
        data=data,
        data_result=data_result,
        array_contract=array_contract,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )

    # Stage 2: Execution — preflight gate, optimization run, serialization
    execution = run_pipeline_execution(
        config=config,
        optimization_source=setup["optimization_source"],
        close=setup["close"],
        open_prices=open_prices,
        split_result=setup["split_result"],
        optimization_evidence=setup["optimization_evidence"],
        recorder=recorder,
    )

    # Stage 3: Publishing — candidates, leaderboard, publish to candidate store
    publishing = run_pipeline_publishing(
        config=config,
        recorder=recorder,
        data_result=data_result,
        array_contract=array_contract,
        optimization_source=setup["optimization_source"],
        optimization_run=execution["optimization_run"],
        run_payload=execution["run_payload"],
        split_result=setup["split_result"],
        portfolio_builtin=setup["portfolio_builtin"],
        optimization_evidence=execution["optimization_evidence"],
        store_path=setup["store_path"],
        metric_registry_fingerprint=metric_registry_fingerprint,
    )

    store_namespace = candidate_store_namespace()

    # Stage 4: Completion — artifact, completion, activation, result
    return run_pipeline_completion(
        config=config,
        recorder=recorder,
        data_result=data_result,
        array_contract=array_contract,
        strategy_evidence=setup["strategy_evidence"],
        optimization_builtin=setup["optimization_builtin"],
        portfolio_builtin=setup["portfolio_builtin"],
        split_result=setup["split_result"],
        optimization_evidence=publishing["optimization_evidence"],
        run_payload=execution["run_payload"],
        candidate_rows=publishing["candidate_rows"],
        leaderboard=publishing["leaderboard"],
        resolved_locks=setup["resolved_locks"],
        lock_records=publishing["lock_records"],
        candidate_store_provenance=publishing["candidate_store_provenance"],
        store_path=setup["store_path"],
        store_namespace=store_namespace,
        optimization_run=execution["optimization_run"],
        metric_registry_fingerprint=metric_registry_fingerprint,
    )

