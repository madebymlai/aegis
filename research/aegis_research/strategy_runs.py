from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from research.aegis_research.component_registry import (
    ComponentSelection,
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
    build_data_array_contract,
    data_array_evidence_payload,
    merge_data_arrays,
    with_data_array_contract_metadata,
)
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.component_source import (
    build_component_optimization_source,
    component_param_slices,
    component_ref_key,
)
from research.aegis_research.optimization.evidence import candidate_rows_from_param_index
from research.aegis_research.optimization.leaderboard import build_optimization_leaderboard
from research.aegis_research.optimization.preflight import (
    PreflightError,
    build_preflight,
)
from research.aegis_research.optimization.promotion import (
    ComponentPromotionRef,
    ResolvedPromotion,
    resolve_component_promotion,
)
from research.aegis_research.optimization.runner import (
    METRIC_INDEX_NAME,
    execute_optimization,
    serialize_optimization_run,
)
from research.aegis_research.optimization.source import (
    OPTIMIZATION_SOURCE_CONTRACT,
    OptimizationSourceError,
)
from research.aegis_research.provenance.experiment_artifacts import ExperimentArtifactWriter
from research.aegis_research.provenance.manifest import atomic_write_json, hash_file
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.provenance.run_store import RunStore
from research.aegis_research.run_splits import build_run_splits_result

STRATEGY_ARTIFACT_SCHEMA_VERSION = "strategy_run.v3"
COMPONENT_PROMOTION_SCHEMA_VERSION = "component_promotion.v1"
COMPONENT_PROMOTION_PROVENANCE_SCHEMA_VERSION = "component_promotion_provenance.v1"


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
    array_contract = _strategy_data_array_contract(config, component_registry)

    recorder = RunStore(config.output_dir).start_run(
        run_label=config.name,
        config=resolved_config.redacted_resolved_config(),
        mode=rerun_mode,
        run_id=run_id,
        parent_run_id=parent_run_id,
        supersedes_run_id=supersedes_run_id,
    )
    recorder.manifest.evidence = {
        "evidence_type": "strategy_sweep",
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
        recorder.mark_run_failed(
            diagnostic=_failure_diagnostic(error, known_secrets=known_secrets)
        )
        raise
    except Exception as error:
        recorder.mark_run_failed(
            diagnostic=_failure_diagnostic(error, known_secrets=known_secrets)
        )
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
    candidate_store_path = _candidate_store_path(config)
    resolved_component_params, resolved_promotions = _resolve_component_promotions(
        config,
        candidate_store_path=candidate_store_path,
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
        "data": _strategy_data_evidence_payload(data_result, array_contract),
        "metric_registry_fingerprint": metric_registry_fingerprint,
        "open_prices_available": open_prices is not None,
        "resolved_promotions": resolved_promotions,
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

    candidate_store_namespace = _candidate_store_namespace()
    candidate_rows = candidate_rows_from_param_index(
        optimization_run.evaluated_index,
        source_identity=optimization_source.evidence,
        data_identity=_candidate_data_identity(data_result, array_contract),
        portfolio_policy=to_builtin(asdict(config.portfolio)),
        store_namespace=candidate_store_namespace,
        coordinate_levels=("split", "set", "symbol", METRIC_INDEX_NAME),
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
    candidate_store_provenance = _candidate_store_provenance(
        recorder,
        optimization_source=optimization_source.evidence,
        data_result=data_result,
        array_contract=array_contract,
        config=config,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    promotion_records = _component_promotion_records(
        run_id=recorder.manifest.run_id,
        leaderboard=leaderboard,
        optimization_source=optimization_source.evidence,
    )
    with CandidateStore(candidate_store_path) as candidate_store:
        candidate_store.insert_completed_run(
            run_id=recorder.manifest.run_id,
            candidate_rows=candidate_rows,
            leaderboard=leaderboard,
            provenance=candidate_store_provenance,
        )
        for promotion in promotion_records:
            candidate_store.insert_promotion(
                token=promotion["token"],
                run_id=promotion["run_id"],
                component_family=promotion["component_family"],
                component_id=promotion["component_id"],
                component_slot=promotion["component_slot"],
                candidate_key=promotion["candidate_key"],
                params=promotion["params"],
                provenance=promotion["provenance"],
            )
    optimization_evidence["promotions"] = promotion_records
    recorder.manifest.evidence["optimization"] = optimization_evidence

    artifact_payload = {
        "schema_version": STRATEGY_ARTIFACT_SCHEMA_VERSION,
        "evidence_type": "optimization",
        "strategy": strategy_evidence,
        "data": _strategy_data_evidence_payload(data_result, array_contract),
        "ranking": {
            "metric": config.ranking.metric,
            "direction": config.ranking.direction,
            "secondary_metrics": list(config.ranking.secondary_metrics),
        },
        "portfolio": to_builtin(asdict(config.portfolio)),
        "optimization": to_builtin(asdict(config.optimization)),
        "split": split_result.metadata,
        "preflight": optimization_evidence["preflight"],
        "execution": run_payload,
        "candidates": [to_builtin(record) for record in candidate_rows],
        "leaderboard": leaderboard,
        "resolved_promotions": resolved_promotions,
        "promotions": promotion_records,
        "candidate_store": {
            "schema_version": "candidate_store_ref.v1",
            "path": candidate_store_namespace["path"],
            "provenance": candidate_store_provenance,
        },
        "metric_registry_fingerprint": metric_registry_fingerprint,
    }
    _write_strategy_artifact(recorder, artifact_payload)
    recorder.mark_run_completed()
    return {
        **_run_refs(recorder),
        "evidence_type": "optimization",
        "strategy_artifact_id": "strategy.run",
        "optimization": {
            "ranking_metric": optimization_run.ranking_metric,
            "ranking_direction": optimization_run.ranking_direction,
            "split_count": split_result.metadata["n_splits"],
            "selection_row_count": len(optimization_run.selection),
            "candidate_count": len(candidate_rows),
        },
    }


def _strategy_data_array_contract(
    config: Any,
    component_registry: FrozenComponentRegistry,
) -> DataArrayContract:
    return build_data_array_contract(
        configured_arrays=config.data.effective_arrays,
        component_required_arrays=_strategy_required_arrays(config, component_registry),
        pipeline_required_arrays=("Close", "Open"),
    )


def _strategy_required_arrays(
    config: Any,
    component_registry: FrozenComponentRegistry,
) -> tuple[str, ...]:
    required = [
        component_registry.get(ComponentSelection("strategies", config.strategy.id)).input_names
    ]
    for ref in config.indicators:
        required.append(
            component_registry.get(ComponentSelection("indicators", ref.id)).input_names
        )
    return merge_data_arrays(*required)


def _strategy_data_evidence_payload(
    data_result: Any,
    array_contract: DataArrayContract,
) -> dict[str, Any]:
    return data_array_evidence_payload(data_result, array_contract) | {
        "strategy_consumed_runner_data": True,
        "strategy_data_binding": "runner_data_bundle",
    }


def _candidate_data_identity(data_result: Any, array_contract: DataArrayContract) -> dict[str, Any]:
    metadata = data_result.metadata
    return {
        "schema_version": "candidate_data_identity.v1",
        "source": metadata.get("source"),
        "requested_symbols": metadata.get("requested_symbols"),
        "symbols": metadata.get("symbols"),
        "timeframe": metadata.get("timeframe"),
        "effective_arrays": metadata.get("effective_arrays"),
        "loaded_arrays": metadata.get("loaded_arrays"),
        "shape": metadata.get("shape"),
        "index_start": metadata.get("index_start"),
        "index_end": metadata.get("index_end"),
        "index_evidence": metadata.get("index_evidence"),
        "source_metadata": metadata.get("source_metadata"),
        "array_contract": array_contract.metadata(),
    }


def _resolve_component_promotions(
    config: Any,
    *,
    candidate_store_path: Path,
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[dict[str, Any]]]:
    refs = list(_component_promotion_refs(config))
    if not refs:
        return {}, []
    resolved_params: dict[tuple[str, str, str], dict[str, Any]] = {}
    resolved_records: list[dict[str, Any]] = []
    with CandidateStore(candidate_store_path) as candidate_store:
        for key, ref in refs:
            resolved = resolve_component_promotion(ref, store=candidate_store)
            if key in resolved_params:
                raise OptimizationSourceError(
                    f"duplicate promotion resolution for component {key}"
                )
            resolved_params[key] = dict(resolved.params)
            resolved_records.append(_resolved_promotion_record(resolved))
    return resolved_params, resolved_records


def _component_promotion_refs(
    config: Any,
) -> Iterator[tuple[tuple[str, str, str], ComponentPromotionRef]]:
    if config.strategy.lock_id is not None or config.strategy.candidate_id is not None:
        key = component_ref_key("strategies", config.strategy.id, "strategy")
        yield key, ComponentPromotionRef(
            component_family="strategies",
            component_id=config.strategy.id,
            component_slot="strategy",
            lock_id=config.strategy.lock_id,
            candidate_id=config.strategy.candidate_id,
        )
    for ref in config.indicators:
        if ref.lock_id is None and ref.candidate_id is None:
            continue
        key = component_ref_key("indicators", ref.id, ref.id)
        yield key, ComponentPromotionRef(
            component_family="indicators",
            component_id=ref.id,
            component_slot=ref.id,
            lock_id=ref.lock_id,
            candidate_id=ref.candidate_id,
        )


def _resolved_promotion_record(resolved: ResolvedPromotion) -> dict[str, Any]:
    return {
        "schema_version": "resolved_component_promotion.v1",
        "reference_kind": resolved.reference_kind,
        "component_family": resolved.component_family,
        "component_id": resolved.component_id,
        "component_slot": resolved.component_slot,
        "candidate_key": resolved.candidate_key,
        "run_id": resolved.run_id,
        "params": to_builtin(resolved.params),
        "provenance": to_builtin(resolved.provenance),
    }


def _component_promotion_records(
    *,
    run_id: str,
    leaderboard: Mapping[str, Any],
    optimization_source: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = list(leaderboard.get("rows", ()))
    if not rows:
        return []
    top_row = rows[0]
    candidate_key = str(top_row["candidate_key"])
    candidate_params = dict(top_row.get("params", {}))
    component_slices = component_param_slices(candidate_params)
    records: list[dict[str, Any]] = []
    for runtime in _promotion_runtime_records(optimization_source):
        component_family = str(runtime["family"])
        component_id = str(runtime["id"])
        component_slot = str(runtime["slot"])
        params = dict(runtime.get("fixed_params", {}))
        slice_key = (component_family, component_id, component_slot)
        params.update(component_slices.get(slice_key, {}))
        missing = sorted(set(runtime.get("param_keys", {})) - set(params))
        if missing:
            raise OptimizationSourceError(
                f"candidate {candidate_key} is missing promotion params for component "
                f"{component_family}/{component_id} slot {component_slot!r}: {missing}"
            )
        token = _component_promotion_token(
            run_id=run_id,
            rank=1,
            component_family=component_family,
            component_id=component_id,
            component_slot=component_slot,
            candidate_key=candidate_key,
        )
        provenance = {
            "schema_version": COMPONENT_PROMOTION_PROVENANCE_SCHEMA_VERSION,
            "run_id": run_id,
            "rank": 1,
            "candidate_key": candidate_key,
            "component_family": component_family,
            "component_id": component_id,
            "component_slot": component_slot,
            "source": optimization_source,
            "leaderboard_row": top_row,
        }
        records.append(
            {
                "schema_version": COMPONENT_PROMOTION_SCHEMA_VERSION,
                "token": token,
                "reference_kind": "lock_id",
                "run_id": run_id,
                "rank": 1,
                "component_family": component_family,
                "component_id": component_id,
                "component_slot": component_slot,
                "candidate_key": candidate_key,
                "params": to_builtin(params),
                "provenance": to_builtin(provenance),
            }
        )
    return records


def _promotion_runtime_records(optimization_source: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtimes: list[dict[str, Any]] = []
    strategy = optimization_source.get("strategy")
    if isinstance(strategy, Mapping):
        runtimes.append(dict(strategy))
    for runtime in optimization_source.get("indicators", ()):
        if isinstance(runtime, Mapping):
            runtimes.append(dict(runtime))
    return runtimes


def _component_promotion_token(
    *,
    run_id: str,
    rank: int,
    component_family: str,
    component_id: str,
    component_slot: str,
    candidate_key: str,
) -> str:
    payload = {
        "schema_version": COMPONENT_PROMOTION_SCHEMA_VERSION,
        "run_id": run_id,
        "rank": rank,
        "component_family": component_family,
        "component_id": component_id,
        "component_slot": component_slot,
        "candidate_key": candidate_key,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()[:32]
    return f"lock_{digest}"


def _candidate_store_path(config: Any) -> Path:
    return Path(config.output_dir) / ".candidate_store" / "candidates.sqlite3"


def _candidate_store_namespace() -> dict[str, str]:
    return {
        "kind": "local_sqlite",
        "path": ".candidate_store/candidates.sqlite3",
    }


def _candidate_store_provenance(
    recorder: Any,
    *,
    optimization_source: dict[str, Any],
    data_result: Any,
    array_contract: DataArrayContract,
    config: Any,
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "candidate_store_provenance.v1",
        "run_id": recorder.manifest.run_id,
        "strategy_artifact_id": "strategy.run",
        "source": optimization_source,
        "data": _candidate_data_identity(data_result, array_contract),
        "portfolio": to_builtin(asdict(config.portfolio)),
        "ranking": {
            "metric": config.ranking.metric,
            "direction": config.ranking.direction,
            "secondary_metrics": list(config.ranking.secondary_metrics),
        },
        "metric_registry_fingerprint": metric_registry_fingerprint,
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


def _write_strategy_artifact(recorder, payload: dict[str, Any]) -> None:
    _plan_strategy_artifact_if_needed(recorder)
    artifact_path = Path("strategy_run.json")
    recorder.artifacts.begin_artifact_write("strategy.run")
    full_path = recorder.run_dir / artifact_path
    atomic_write_json(full_path, payload)
    recorder.artifacts.complete_artifact(
        "strategy.run",
        content_hash=hash_file(full_path),
        size=full_path.stat().st_size,
        shape=_strategy_artifact_shape(payload),
    )


def _plan_strategy_artifact_if_needed(recorder: Any) -> None:
    if _strategy_artifact_record(recorder) is not None:
        return
    recorder.artifacts.plan_artifact(
        artifact_id="strategy.run",
        role="strategy_sweep_evidence",
        artifact_type="json",
        producer_stage="strategy_run",
        path="strategy_run.json",
        schema_version=STRATEGY_ARTIFACT_SCHEMA_VERSION,
    )


def _strategy_artifact_record(recorder: Any) -> dict[str, Any] | None:
    for artifact in recorder.manifest.artifacts:
        if artifact["id"] == "strategy.run":
            return artifact
    return None


def _strategy_artifact_shape(payload: dict[str, Any]) -> dict[str, int]:
    shape = {
        "leaderboard_rows": len(payload["leaderboard"]["rows"]),
        "candidate_count": len(payload.get("candidates", [])),
    }
    if "split" in payload:
        shape["split_count"] = int(payload["split"].get("n_splits", 0))
    return shape
