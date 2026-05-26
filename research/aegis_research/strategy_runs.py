from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
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
    SignalConfig,
    known_config_secret_values,
    redact_text,
    to_builtin,
)
from research.aegis_research.data import (
    MarketDataBundle,
    load_market_data_result,
    market_data_bundle,
)
from research.aegis_research.data_arrays import (
    DataArrayContract,
    with_data_array_contract_metadata,
)
from research.aegis_research.optimization.candidate_publishing import (
    activate_candidate_run,
    build_candidate_store_provenance,
    candidate_store_namespace,
    candidate_store_path,
    publish_candidates,
)
from research.aegis_research.optimization.component_source import (
    build_component_optimization_source,
)
from research.aegis_research.optimization.evidence import candidate_rows_from_param_index
from research.aegis_research.optimization.leaderboard import build_optimization_leaderboard
from research.aegis_research.optimization.preflight import (
    PreflightError,
    build_preflight,
)
from research.aegis_research.optimization.lock_resolution import (
    build_component_lock_records,
    resolve_component_locks,
)
from research.aegis_research.optimization.run_data_contract import (
    build_candidate_data_identity,
    build_run_data_array_contract,
    build_run_data_evidence_payload,
)
from research.aegis_research.optimization.run_artifacts import (
    build_strategy_artifact_payload,
    write_strategy_artifact,
)
from research.aegis_research.optimization.runner import (
    execute_optimization,
    serialize_optimization_run,
)
from research.aegis_research.optimization.source import (
    OPTIMIZATION_SOURCE_CONTRACT,
    OptimizationSourceError,
)
from research.aegis_research.provenance.experiment_artifacts import ExperimentArtifactWriter
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.provenance.run_store import RunStore
from research.aegis_research.run_splits import build_run_splits_result

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
            on_run_started(_run_refs(recorder))
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
    config: Any,
    *,
    component_registry: FrozenComponentRegistry,
    recorder: Any,
    data_result: Any,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    store_path = candidate_store_path(config)
    resolved_component_params, resolved_locks = resolve_component_locks(
        config,
        candidate_store_path=store_path,
    )
    optimization_source = build_component_optimization_source(
        config,
        component_registry=component_registry,
        data=data,
        resolved_component_params=resolved_component_params,
    )
    strategy_evidence = optimization_source.evidence["strategy"]
    close = data.feature("Close")
    split_result = build_run_splits_result(close.index, config.optimization.split)
    optimization_evidence = {
        "schema_version": "optimization_route.v1",
        "contract": OPTIMIZATION_SOURCE_CONTRACT,
        "source": optimization_source.evidence,
        "param_names": list(optimization_source.params),
        "optimization": to_builtin(asdict(config.optimization)),
        "split": split_result.metadata,
        "data": build_run_data_evidence_payload(data_result, array_contract),
        "metric_registry_fingerprint": metric_registry_fingerprint,
        "open_prices_available": open_prices is not None,
        "resolved_locks": resolved_locks,
    }
    try:
        optimization_evidence["preflight"] = build_preflight(
            params=optimization_source.params,
            optimization=config.optimization,
            split_result=split_result,
            symbol_count=len(close.columns),
            has_open_prices=open_prices is not None,
        )
    except PreflightError as error:
        optimization_evidence["preflight"] = error.diagnostics
        optimization_evidence["preflight_failure"] = {
            "error_type": type(error).__name__,
            "message": str(error),
        }
        recorder.manifest.evidence["optimization"] = optimization_evidence
        recorder.persist()
        raise OptimizationSourceError(str(error)) from error

    try:
        optimization_run = execute_optimization(
            close=close,
            open_prices=open_prices,
            source=optimization_source,
            optimization=config.optimization,
            portfolio=config.portfolio,
            signal=SignalConfig(),
            report=config.report,
            ranking=config.ranking,
            mono_chunk_len=optimization_evidence["preflight"]["computed_mono_chunk_len"],
        )
    except Exception as error:
        optimization_evidence["execution_failure"] = {
            "error_type": type(error).__name__,
            "message": str(error)[:1000],
        }
        recorder.manifest.evidence["optimization"] = optimization_evidence
        recorder.persist()
        raise

    run_payload = serialize_optimization_run(optimization_run)
    optimization_evidence["execution"] = run_payload

    store_namespace = candidate_store_namespace()
    candidate_rows = candidate_rows_from_param_index(
        optimization_run.evaluated_index,
        source_identity=optimization_source.evidence,
        data_identity=build_candidate_data_identity(data_result, array_contract),
        portfolio_policy=to_builtin(asdict(config.portfolio)),
        store_namespace=store_namespace,
        coordinate_levels=("split", "set", "symbol"),
    )
    optimization_evidence["candidate_count"] = len(candidate_rows)
    optimization_evidence["sampled_row_count"] = len(run_payload["sampled_rows"]["rows"])
    optimization_evidence["sampled_rows_source"] = optimization_run.sampled_rows_source
    split_held_out_row_counts = {
        index: len(split.held_out_index) for index, split in enumerate(split_result.splits)
    }
    leaderboard = build_optimization_leaderboard(
        selection=optimization_run.selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts=split_held_out_row_counts,
        ranking_metric=optimization_run.ranking_metric,
        ranking_direction=optimization_run.ranking_direction,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    candidate_store_provenance = build_candidate_store_provenance(
        recorder,
        optimization_source=optimization_source.evidence,
        data_result=data_result,
        array_contract=array_contract,
        config=config,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    lock_records = build_component_lock_records(
        run_id=recorder.manifest.run_id,
        leaderboard=leaderboard,
        optimization_source=optimization_source.evidence,
    )
    publish_candidates(
        store_path,
        run_id=recorder.manifest.run_id,
        candidate_rows=candidate_rows,
        leaderboard=leaderboard,
        provenance=candidate_store_provenance,
        lock_records=lock_records,
    )
    optimization_evidence["locks"] = lock_records
    recorder.manifest.evidence["optimization"] = optimization_evidence

    artifact_payload = build_strategy_artifact_payload(
        strategy_evidence=strategy_evidence,
        data_result=data_result,
        array_contract=array_contract,
        ranking={
            "metric": config.ranking.metric,
            "direction": config.ranking.direction,
            "secondary_metrics": list(config.ranking.secondary_metrics),
        },
        portfolio=to_builtin(asdict(config.portfolio)),
        optimization=to_builtin(asdict(config.optimization)),
        split_metadata=split_result.metadata,
        preflight=optimization_evidence["preflight"],
        execution=run_payload,
        candidates=[to_builtin(record) for record in candidate_rows],
        leaderboard=leaderboard,
        resolved_locks=resolved_locks,
        lock_records=lock_records,
        candidate_store_path=store_namespace["path"],
        candidate_store_provenance=candidate_store_provenance,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    write_strategy_artifact(recorder, artifact_payload)
    recorder.mark_run_completed()
    activate_candidate_run(store_path, recorder.manifest.run_id)
    return {
        **_run_refs(recorder),
        "strategy_artifact_id": "strategy.run",
        "strategy_artifact_path": str(recorder.run_dir / "strategy_run.json"),
        "candidate_store_path": str(store_path),
        "locks": lock_records,
        "optimization": {
            "ranking_metric": optimization_run.ranking_metric,
            "ranking_direction": optimization_run.ranking_direction,
            "split_count": split_result.metadata["n_splits"],
            "selection_row_count": len(optimization_run.selection),
            "candidate_count": len(candidate_rows),
        },
        "leaderboard": leaderboard,
    }


def _run_refs(recorder) -> dict[str, Any]:
    return {
        "run_id": recorder.manifest.run_id,
        "run_dir": str(recorder.run_dir),
        "manifest_path": str(recorder.manifest_path),
        "status": recorder.manifest.status,
        "started_at": recorder.manifest.started_at,
        "finished_at": recorder.manifest.finished_at,
    }
