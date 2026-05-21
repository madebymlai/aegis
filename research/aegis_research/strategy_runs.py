from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from research.aegis_research.candidate_sweeps import (
    CANDIDATE_LEVEL,
    PLAYBOOK_SWEEP_CONTRACT,
    PLAYBOOK_SWEEP_RESULT_SCHEMA,
    SYMBOL_LEVEL,
    CandidateAxis,
    CandidateSweepError,
    ComposedCandidate,
    IndicatorSweepResult,
    compose_candidate_grid,
    materialize_strategy_sweep_signals,
    preflight_indicator_grid,
    validate_indicator_sweep_result,
    validate_strategy_sweep_plan,
)
from research.aegis_research.component_registry import (
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.config import (
    ConfigValidationError,
    ResolvedLaneConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    SignalConfig,
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
from research.aegis_research.playbook_registry import (
    FrozenPlaybookRegistry,
    PlaybookSelection,
    discover_playbook_registry,
)
from research.aegis_research.portfolios import simulate_portfolio, simulate_portfolio_batch
from research.aegis_research.provenance.experiment_artifacts import ExperimentArtifactWriter
from research.aegis_research.provenance.manifest import ArtifactStatus, atomic_write_json, hash_file
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.provenance.run_store import RunStore
from research.aegis_research.reports import portfolio_metrics, portfolio_metrics_by_candidate_group
from research.aegis_research.run_leaderboard import (
    METRIC_SOURCE_CENTRAL_PORTFOLIO,
    build_run_leaderboard,
)
from research.aegis_research.run_splits import RunSplit, build_run_splits_result
from research.aegis_research.split_leaderboard import build_split_leaderboard

STRATEGY_ARTIFACT_SCHEMA_VERSION = "strategy_run.v3"
STRATEGY_OUTPUT_FORBIDDEN_KEYS = {
    "costs",
    "direction",
    "entry_budget",
    "execution_timing",
    "fees",
    "portfolio",
    "price",
    "size",
    "sizing",
    "slippage",
}
PLAYBOOK_METRIC_SOURCE_KEYS = {
    "baseline_metric_source",
    "baseline_metrics",
    "metric_source",
    "metrics",
}
INDICATOR_CANDIDATE_FORBIDDEN_KEYS = (
    PLAYBOOK_METRIC_SOURCE_KEYS
    | STRATEGY_OUTPUT_FORBIDDEN_KEYS
    | {
        "entries",
        "exits",
    }
)


@dataclass(frozen=True)
class StrategyInputs:
    data: MarketDataBundle
    indicators: Mapping[str, Any]
    metadata: dict[str, Any]


class StrategyIndicatorInputs(Mapping[str, Any]):
    def __init__(
        self,
        values: Mapping[str, Any],
        *,
        required_consumed_keys: Iterable[str] = (),
    ) -> None:
        self._values = dict(values)
        self._required_consumed_keys = tuple(required_consumed_keys)
        self._consumed_keys: set[str] = set()

    @property
    def consumed_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._consumed_keys))

    @property
    def missing_required_keys(self) -> tuple[str, ...]:
        return tuple(
            key for key in self._required_consumed_keys if key not in self._consumed_keys
        )

    def __getitem__(self, key: str) -> Any:
        value = self._values[key]
        if key in self._required_consumed_keys and isinstance(value, Mapping):
            return _TrackedIndicatorCandidate(key, value, self._mark_consumed)
        return value

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def _mark_consumed(self, key: str) -> None:
        if key in self._values:
            self._consumed_keys.add(key)


class _TrackedIndicatorCandidate(Mapping[str, Any]):
    def __init__(
        self,
        key: str,
        value: Mapping[str, Any],
        mark_consumed: Callable[[str], None],
    ) -> None:
        self._key = key
        self._value = value
        self._mark_consumed = mark_consumed

    def __getitem__(self, item: str) -> Any:
        if item == "outputs":
            outputs = self._value[item]
            if isinstance(outputs, Mapping):
                return _TrackedIndicatorOutputs(self._key, outputs, self._mark_consumed)
        return self._value[item]

    def __contains__(self, item: object) -> bool:
        return item in self._value

    def __iter__(self) -> Iterator[str]:
        return iter(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except KeyError:
            return default


class _TrackedIndicatorOutputs(Mapping[str, Any]):
    def __init__(
        self,
        key: str,
        value: Mapping[str, Any],
        mark_consumed: Callable[[str], None],
    ) -> None:
        self._key = key
        self._value = value
        self._mark_consumed = mark_consumed

    def __getitem__(self, item: str) -> Any:
        value = self._value[item]
        self._mark_consumed(self._key)
        return value

    def __contains__(self, item: object) -> bool:
        return item in self._value

    def __iter__(self) -> Iterator[str]:
        return iter(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except KeyError:
            return default


@dataclass(frozen=True)
class StrategySignalResult:
    entries: pd.DataFrame
    exits: pd.DataFrame
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class IndicatorContext:
    context_id: str
    indicators: dict[str, Any]
    evidence: list[dict[str, Any]]
    candidate_evidence: list[dict[str, Any]]
    required_indicator_keys: tuple[str, ...]


def run_strategy_sweep(
    resolved_config: ResolvedLaneConfig,
    *,
    component_registry: FrozenComponentRegistry,
    playbook_registry: FrozenPlaybookRegistry | None = None,
    rerun_mode: str = RerunMode.NEW,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    supersedes_run_id: str | None = None,
    on_run_started: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    config = resolved_config.config
    if config.lane != "run":
        raise ValueError("run_strategy_sweep requires a run lane config")
    playbooks = playbook_registry or discover_playbook_registry(
        component_registry=component_registry
    )
    array_contract = _strategy_data_array_contract(config, component_registry, playbooks)

    recorder = RunStore(config.output_dir).start_run(
        run_label=config.name,
        config=resolved_config.redacted_resolved_config(),
        mode=rerun_mode,
        run_id=run_id,
        parent_run_id=parent_run_id,
        supersedes_run_id=supersedes_run_id,
    )
    recorder.manifest.evidence = {
        "lane": "run",
        "evidence_type": "strategy_sweep",
        "component_registry_fingerprint": component_registry.fingerprint,
        "playbook_registry_fingerprint": playbooks.fingerprint,
        "data_arrays": array_contract.metadata(),
    }
    recorder.persist()
    if on_run_started is not None:
        on_run_started(_run_refs(recorder))

    try:
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
        if config.strategy.source == "playbook":
            _assert_playbook_sweep_strategy(config.strategy, playbooks)
            return _run_playbook_strategy_sweep(
                config,
                component_registry=component_registry,
                playbook_registry=playbooks,
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
        indicators, indicator_evidence = _resolve_indicator_refs(
            config.indicators,
            component_registry=component_registry,
            data=data_bundle,
        )
        composition_diagnostics = _composition_diagnostics()
        recorder.manifest.evidence["composition"] = composition_diagnostics["planned"]
        recorder.persist()
        indicator_contexts = _fixed_indicator_contexts(indicators, indicator_evidence)
        if config.split is not None:
            return _run_split_component_strategy_sweep(
                config,
                component_registry=component_registry,
                recorder=recorder,
                data_result=data_result,
                data=data_bundle,
                open_prices=open_prices,
                array_contract=array_contract,
                indicator_contexts=indicator_contexts,
                composition_diagnostics=composition_diagnostics,
                metric_registry_fingerprint=(
                    resolved_config.metric_registry.fingerprint
                    if resolved_config.metric_registry
                    else None
                ),
            )

        strategy_evidence, strategy_candidate_records, signal_diagnostics, portfolio_diagnostics = (
            _resolve_strategy_ref(
                config.strategy,
                component_registry=component_registry,
                data=data_bundle,
                open_prices=open_prices,
                indicator_contexts=indicator_contexts,
                portfolio_config=config.portfolio,
                report_config=config.report,
                composition_diagnostics=composition_diagnostics,
            )
        )
        _assert_unique_strategy_variant_ids(strategy_candidate_records)
        leaderboard = build_run_leaderboard(
            strategy_candidate_records,
            metric=config.ranking.metric,
            direction=config.ranking.direction,
            secondary_metrics=config.ranking.secondary_metrics,
            metric_registry_fingerprint=(
                resolved_config.metric_registry.fingerprint if resolved_config.metric_registry else None
            ),
        )
        _assert_leaderboard_complete(leaderboard)
        payload = {
            "schema_version": STRATEGY_ARTIFACT_SCHEMA_VERSION,
            "lane": "run",
            "evidence_type": "strategy_sweep",
            "strategy": strategy_evidence,
            "indicators": indicator_evidence,
            "data": _strategy_data_evidence_payload(
                data_result,
                array_contract,
                strategy_source=config.strategy.source,
            ),
            "candidates": [to_builtin(record) for record in strategy_candidate_records],
            "leaderboard": leaderboard,
            "composition": composition_diagnostics,
            "signal_diagnostics": signal_diagnostics,
            "portfolio_diagnostics": portfolio_diagnostics,
        }
        _write_strategy_artifact(recorder, payload)
        recorder.mark_run_completed()
        return {
            **_run_refs(recorder),
            "lane": "run",
            "evidence_type": "strategy_sweep",
            "strategy_artifact_id": "strategy.run",
            "leaderboard": leaderboard,
        }
    except KeyboardInterrupt:
        recorder.mark_run_interrupted(
            diagnostic={"error_type": "KeyboardInterrupt", "message": "interrupted"}
        )
        raise
    except ConfigValidationError as error:
        recorder.mark_run_failed(
            diagnostic={"error_type": type(error).__name__, "message": str(error)[:1000]}
        )
        raise
    except Exception as error:
        recorder.mark_run_failed(
            diagnostic={"error_type": type(error).__name__, "message": str(error)[:1000]}
        )
        raise


def _resolve_indicator_refs(
    refs: list[RunIndicatorSourceConfig],
    *,
    component_registry: FrozenComponentRegistry,
    data: MarketDataBundle,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    indicators: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []
    for ref in refs:
        if ref.source == "component":
            component_ids = ref.expanded_ids(component_registry.ids("indicators"))
            for component_id in component_ids:
                if component_id in indicators:
                    raise ValueError(f"duplicate indicator component ref: {component_id}")
                output, source_evidence = _load_component_indicator_ref(
                    component_id,
                    component_registry=component_registry,
                    data=data,
                )
                indicators[component_id] = output
                evidence.append(source_evidence)
            continue

        raise ValueError(
            "playbook indicators in run configs require a playbook strategy sweep; "
            f"playbook indicator ids {ref.ids!r} cannot enter the component runner"
        )
    return indicators, evidence


def _assert_playbook_sweep_strategy(
    ref: RunSourceRefConfig,
    playbook_registry: FrozenPlaybookRegistry,
) -> None:
    definition = playbook_registry.get(PlaybookSelection("strategies", ref.id))
    if definition.manifest.result_schema != PLAYBOOK_SWEEP_RESULT_SCHEMA:
        raise ValueError(
            f"strategy playbook {definition.id!r} uses result_schema "
            f"{definition.manifest.result_schema!r}; run playbooks must use "
            f"{PLAYBOOK_SWEEP_RESULT_SCHEMA!r}"
        )


def _run_playbook_strategy_sweep(
    config: Any,
    *,
    component_registry: FrozenComponentRegistry,
    playbook_registry: FrozenPlaybookRegistry,
    recorder: Any,
    data_result: Any,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    try:
        indicators, indicator_evidence, indicator_axes, indicator_candidate_evidence, preflight = (
            _resolve_sweep_indicator_refs(
                config.indicators,
                component_registry=component_registry,
                playbook_registry=playbook_registry,
                data=data,
                candidate_grid=config.candidate_grid,
            )
        )
    except CandidateSweepError as error:
        _persist_sweep_preflight_failure(recorder, error)
        raise
    strategy_definition = playbook_registry.get(PlaybookSelection("strategies", config.strategy.id))
    inputs = StrategyInputs(
        data=data,
        indicators=StrategyIndicatorInputs(
            indicators,
            required_consumed_keys=tuple(_indicator_source_key(axis.source_id) for axis in indicator_axes),
        ),
        metadata={
            "strategy_id": strategy_definition.id,
            "playbook_source_hash": strategy_definition.identity.source_hash,
            "sweep_contract": PLAYBOOK_SWEEP_CONTRACT,
        },
    )
    strategy_plan = validate_strategy_sweep_plan(
        strategy_definition.load_callable()(inputs),
        source_id=strategy_definition.id,
    )
    total_composed_candidates = _sweep_composed_candidate_count(
        strategy_plan.axis,
        indicator_axes,
    )
    close = data.feature("Close")
    batch_count = _candidate_batch_count(
        total_composed_candidates,
        config.candidate_grid.batch_size,
    )
    composition_diagnostics = {
        "schema_version": "strategy_sweep_composition.v1",
        "planned": {
            "indicator_preflight": preflight,
            "strategy_candidate_count": strategy_plan.axis.count,
            "total_composed_candidates": total_composed_candidates,
            "batch_size": config.candidate_grid.batch_size,
            "batch_count": batch_count,
            "execution_preflight": _sweep_execution_preflight(
                total_composed_candidates=total_composed_candidates,
                batch_size=config.candidate_grid.batch_size,
                row_count=len(close.index),
                symbol_count=len(close.columns),
                has_open_prices=open_prices is not None,
                max_estimated_cells=config.candidate_grid.max_estimated_cells,
            ),
        },
        "total_composed_candidates": total_composed_candidates,
    }
    recorder.manifest.evidence["composition"] = composition_diagnostics["planned"]
    recorder.persist()
    _assert_sweep_candidate_budget(
        total_composed_candidates,
        config.candidate_grid.max_candidates,
    )
    _assert_sweep_execution_budget(
        composition_diagnostics["planned"]["execution_preflight"]
    )
    composed_candidates = compose_candidate_grid(
        strategy_axis=strategy_plan.axis,
        indicator_axes=indicator_axes,
    )
    strategy_evidence = {
        "source": "playbook",
        "id": strategy_definition.id,
        "version": strategy_definition.manifest.version,
        **strategy_definition.identity.public(),
        "consumes_runner_data": True,
        "data_binding": "strategy_sweep_inputs",
        "result_contract": PLAYBOOK_SWEEP_CONTRACT,
    }
    catalogs = _sweep_artifact_catalogs(
        strategy_evidence=strategy_evidence,
        indicator_evidence=indicator_evidence,
        indicator_candidate_evidence=indicator_candidate_evidence,
        strategy_axis=strategy_plan.axis,
        composed_candidates=composed_candidates,
    )
    strategy_records: list[dict[str, Any]] = []
    signal_diagnostics = _empty_signal_diagnostics()
    portfolio_diagnostics = _empty_portfolio_diagnostics()
    chunk_diagnostics = _empty_chunk_diagnostics()
    recorder.manifest.evidence["chunks"] = chunk_diagnostics
    recorder.persist()
    if config.split is not None:
        return _run_split_playbook_strategy_sweep(
            config,
            recorder=recorder,
            data_result=data_result,
            data=data,
            open_prices=open_prices,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry_fingerprint,
            strategy_definition=strategy_definition,
            strategy_plan=strategy_plan,
            indicator_axes=indicator_axes,
            indicator_evidence=indicator_evidence,
            indicator_candidate_evidence=indicator_candidate_evidence,
            composed_candidates=composed_candidates,
            catalogs=catalogs,
            strategy_evidence=strategy_evidence,
            composition_diagnostics=composition_diagnostics,
            signal_diagnostics=signal_diagnostics,
            portfolio_diagnostics=portfolio_diagnostics,
            chunk_diagnostics=chunk_diagnostics,
            inputs=inputs,
        )
    for batch_index, batch in enumerate(
        _candidate_batches(composed_candidates, config.candidate_grid.batch_size)
    ):
        batch_ids = tuple(candidate.candidate_id for candidate in batch)
        chunk_ref = _sweep_chunk_ref(batch_index)
        chunk_record = _sweep_chunk_record(batch_index, batch_ids, chunk_ref)
        chunk_diagnostics["chunks"].append(chunk_record)
        catalogs["chunks"][chunk_ref] = chunk_record
        recorder.persist()
        try:
            chunk_record["stage"] = "materialize_signals"
            signal_result = materialize_strategy_sweep_signals(
                strategy_plan,
                source_id=strategy_definition.id,
                requested_candidate_ids=batch_ids,
                indicator_axes=indicator_axes,
                candidate_pool=batch,
                close=close,
            )
            chunk_record["stage"] = "indicator_consumption_validation"
            _assert_strategy_consumed_indicator_context(inputs, strategy_id=strategy_definition.id)
            chunk_record["stage"] = "portfolio_simulation"
            portfolio = simulate_portfolio_batch(
                close,
                signal_result.entries,
                signal_result.exits,
                config.portfolio,
                SignalConfig(),
                open_prices=open_prices,
                market_index=close.index,
            )
            chunk_record["stage"] = "metric_extraction"
            metrics_by_candidate = portfolio_metrics_by_candidate_group(
                portfolio.portfolio,
                config.report,
                batch_ids,
            )
            chunk_record["stage"] = "candidate_recording"
            for candidate in batch:
                strategy_candidate_ref = _strategy_candidate_ref(candidate.strategy)
                indicator_candidate_refs = [
                    _indicator_candidate_ref(indicator) for indicator in candidate.indicators
                ]
                metric_ref = candidate.candidate_id
                catalogs["metrics"][metric_ref] = metrics_by_candidate[candidate.candidate_id]
                catalogs["composed_candidates"][candidate.candidate_id] |= {
                    "chunk_ref": chunk_ref,
                    "metric_ref": metric_ref,
                }
                indicator_candidates = [
                    indicator_candidate_evidence[
                        (indicator.source, indicator.source_id, indicator.candidate_id)
                    ]
                    for indicator in candidate.indicators
                ]
                strategy_records.append(
                    {
                        "variant_id": candidate.candidate_id,
                        "composed_candidate_id": candidate.candidate_id,
                        "strategy_source": "playbook",
                        "strategy_id": strategy_definition.id,
                        "strategy_candidate_id": candidate.strategy.candidate_id,
                        "strategy_candidate_ref": strategy_candidate_ref,
                        "strategy_params": to_builtin(candidate.strategy.params),
                        "source_hash": strategy_definition.identity.source_hash,
                        "indicators": indicator_evidence,
                        "indicator_candidates": indicator_candidates,
                        "indicator_candidate_refs": indicator_candidate_refs,
                        "metric_ref": metric_ref,
                        "chunk_ref": chunk_ref,
                        "params": to_builtin(candidate.strategy.params),
                        "metrics": metrics_by_candidate[candidate.candidate_id],
                        "metric_source": METRIC_SOURCE_CENTRAL_PORTFOLIO,
                        "portfolio": to_builtin(asdict(config.portfolio)),
                    }
                )
                signal_diagnostics["candidates"][candidate.candidate_id] = {
                    **signal_result.diagnostics,
                    "batch_index": batch_index,
                    "chunk_ref": chunk_ref,
                }
                portfolio_diagnostics["candidates"][candidate.candidate_id] = {
                    "batch_index": batch_index,
                    "chunk_ref": chunk_ref,
                }
            portfolio_diagnostics["chunks"][chunk_ref] = to_builtin(portfolio.diagnostics)
        except Exception as error:
            _mark_sweep_chunk_failed(chunk_record, error)
            recorder.persist()
            raise
        chunk_record["status"] = "succeeded"
        chunk_record["stage"] = "completed"
        recorder.persist()

    leaderboard = build_run_leaderboard(
        strategy_records,
        metric=config.ranking.metric,
        direction=config.ranking.direction,
        secondary_metrics=config.ranking.secondary_metrics,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    _assert_leaderboard_complete(leaderboard)
    payload = {
        "schema_version": STRATEGY_ARTIFACT_SCHEMA_VERSION,
        "lane": "run",
        "evidence_type": "strategy_sweep",
        "strategy": strategy_evidence,
        "indicators": indicator_evidence,
        "data": _strategy_data_evidence_payload(
            data_result,
            array_contract,
            strategy_source=config.strategy.source,
        ),
        "candidates": _compact_sweep_candidate_records(catalogs),
        "leaderboard": leaderboard,
        "composition": composition_diagnostics,
        "catalogs": catalogs,
        "chunk_diagnostics": chunk_diagnostics,
        "signal_diagnostics": signal_diagnostics,
        "portfolio_diagnostics": portfolio_diagnostics,
    }
    _write_strategy_artifact(recorder, payload)
    recorder.mark_run_completed()
    return {
        **_run_refs(recorder),
        "lane": "run",
        "evidence_type": "strategy_sweep",
        "strategy_artifact_id": "strategy.run",
        "leaderboard": leaderboard,
    }


def _run_split_playbook_strategy_sweep(
    config: Any,
    *,
    recorder: Any,
    data_result: Any,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    strategy_definition: Any,
    strategy_plan: Any,
    indicator_axes: list[CandidateAxis],
    indicator_evidence: list[dict[str, Any]],
    indicator_candidate_evidence: dict[tuple[str, str, str], dict[str, Any]],
    composed_candidates: tuple[ComposedCandidate, ...],
    catalogs: dict[str, Any],
    strategy_evidence: dict[str, Any],
    composition_diagnostics: dict[str, Any],
    signal_diagnostics: dict[str, Any],
    portfolio_diagnostics: dict[str, Any],
    chunk_diagnostics: dict[str, Any],
    inputs: StrategyInputs,
) -> dict[str, Any]:
    close = data.feature("Close")
    split_result = build_run_splits_result(close.index, config.split)
    recorder.manifest.evidence["split"] = split_result.metadata
    split_execution_preflight = _split_execution_preflight(
        splits=split_result.splits,
        candidate_count=len(composed_candidates),
        batch_size=config.candidate_grid.batch_size,
        symbol_count=len(close.columns),
        has_open_prices=open_prices is not None,
        max_estimated_cells=config.candidate_grid.max_estimated_cells,
    )
    composition_diagnostics["planned"]["split_execution_preflight"] = split_execution_preflight
    _assert_split_execution_budget(split_execution_preflight)
    _plan_strategy_artifact_if_needed(recorder)
    recorder.persist()
    candidate_records: dict[str, dict[str, Any]] = {}
    split_metric_records: list[dict[str, Any]] = []
    batches = tuple(_candidate_batches(composed_candidates, config.candidate_grid.batch_size))
    for batch_index, batch in enumerate(batches):
        batch_ids = tuple(candidate.candidate_id for candidate in batch)
        chunk_ref = _sweep_chunk_ref(batch_index)
        chunk_record = _sweep_chunk_record(batch_index, batch_ids, chunk_ref)
        chunk_diagnostics["chunks"].append(chunk_record)
        catalogs["chunks"][chunk_ref] = chunk_record
        recorder.persist()
        try:
            chunk_record["stage"] = "materialize_signals"
            signal_result = materialize_strategy_sweep_signals(
                strategy_plan,
                source_id=strategy_definition.id,
                requested_candidate_ids=batch_ids,
                indicator_axes=indicator_axes,
                candidate_pool=batch,
                close=close,
            )
            chunk_record["stage"] = "indicator_consumption_validation"
            _assert_strategy_consumed_indicator_context(inputs, strategy_id=strategy_definition.id)
            chunk_record["stage"] = "split_portfolio_simulation"
            metric_records, split_portfolio_diagnostics = _split_metric_records_for_batch(
                close,
                open_prices,
                signal_result.entries,
                signal_result.exits,
                batch_ids,
                split_result.splits,
                portfolio_config=config.portfolio,
                report_config=config.report,
                roles=("selection",),
            )
            split_metric_records.extend(metric_records)
            portfolio_diagnostics["chunks"][chunk_ref] = split_portfolio_diagnostics
            chunk_record["stage"] = "candidate_recording"
            for candidate in batch:
                strategy_candidate_ref = _strategy_candidate_ref(candidate.strategy)
                indicator_candidate_refs = [
                    _indicator_candidate_ref(indicator) for indicator in candidate.indicators
                ]
                indicator_candidates = [
                    indicator_candidate_evidence[
                        (indicator.source, indicator.source_id, indicator.candidate_id)
                    ]
                    for indicator in candidate.indicators
                ]
                catalogs["composed_candidates"][candidate.candidate_id] |= {"chunk_ref": chunk_ref}
                candidate_records[candidate.candidate_id] = {
                    "variant_id": candidate.candidate_id,
                    "composed_candidate_id": candidate.candidate_id,
                    "strategy_source": "playbook",
                    "strategy_id": strategy_definition.id,
                    "strategy_candidate_id": candidate.strategy.candidate_id,
                    "strategy_candidate_ref": strategy_candidate_ref,
                    "strategy_params": to_builtin(candidate.strategy.params),
                    "source_hash": strategy_definition.identity.source_hash,
                    "indicators": indicator_evidence,
                    "indicator_candidates": indicator_candidates,
                    "indicator_candidate_refs": indicator_candidate_refs,
                    "chunk_ref": chunk_ref,
                    "params": to_builtin(candidate.strategy.params),
                    "metric_source": METRIC_SOURCE_CENTRAL_PORTFOLIO,
                    "portfolio": to_builtin(asdict(config.portfolio)),
                }
                signal_diagnostics["candidates"][candidate.candidate_id] = {
                    **signal_result.diagnostics,
                    "batch_index": batch_index,
                    "chunk_ref": chunk_ref,
                }
                portfolio_diagnostics["candidates"][candidate.candidate_id] = {
                    "batch_index": batch_index,
                    "chunk_ref": chunk_ref,
                }
        except Exception as error:
            _mark_sweep_chunk_failed(chunk_record, error)
            _write_partial_split_strategy_artifact(
                recorder,
                _split_strategy_payload(
                    config,
                    data_result=data_result,
                    array_contract=array_contract,
                    strategy_evidence=strategy_evidence,
                    indicator_evidence=indicator_evidence,
                    candidates=list(candidate_records.values()),
                    leaderboard=None,
                    composition_diagnostics=composition_diagnostics,
                    split_metadata=split_result.metadata,
                    split_metric_records=split_metric_records,
                    catalogs=catalogs,
                    chunk_diagnostics=chunk_diagnostics,
                    signal_diagnostics=signal_diagnostics,
                    portfolio_diagnostics=portfolio_diagnostics,
                ),
                error=error,
            )
            recorder.persist()
            raise
        chunk_record["status"] = "succeeded"
        chunk_record["stage"] = "completed"
        recorder.persist()

    selected_candidate_ids_by_split = _selected_candidate_ids_by_split(
        split_metric_records,
        metric=config.ranking.metric,
        direction=config.ranking.direction,
    )
    for batch_index, batch in enumerate(batches):
        batch_ids = tuple(candidate.candidate_id for candidate in batch)
        selected_batch_ids = tuple(
            candidate_id
            for candidate_id in batch_ids
            if any(candidate_id in selected for selected in selected_candidate_ids_by_split.values())
        )
        if not selected_batch_ids:
            continue
        chunk_ref = _sweep_chunk_ref(batch_index)
        chunk_record = chunk_diagnostics["chunks"][batch_index]
        try:
            chunk_record["stage"] = "materialize_selected_held_out_signals"
            signal_result = materialize_strategy_sweep_signals(
                strategy_plan,
                source_id=strategy_definition.id,
                requested_candidate_ids=selected_batch_ids,
                indicator_axes=indicator_axes,
                candidate_pool=batch,
                close=close,
            )
            chunk_record["stage"] = "split_held_out_portfolio_simulation"
            held_out_records, held_out_diagnostics = _split_metric_records_for_batch(
                close,
                open_prices,
                signal_result.entries,
                signal_result.exits,
                selected_batch_ids,
                split_result.splits,
                portfolio_config=config.portfolio,
                report_config=config.report,
                roles=("held_out",),
                candidate_ids_by_split=selected_candidate_ids_by_split,
            )
            split_metric_records.extend(held_out_records)
            _merge_split_portfolio_diagnostics(
                portfolio_diagnostics["chunks"].setdefault(chunk_ref, {}),
                held_out_diagnostics,
            )
        except Exception as error:
            _mark_sweep_chunk_failed(chunk_record, error)
            _write_partial_split_strategy_artifact(
                recorder,
                _split_strategy_payload(
                    config,
                    data_result=data_result,
                    array_contract=array_contract,
                    strategy_evidence=strategy_evidence,
                    indicator_evidence=indicator_evidence,
                    candidates=list(candidate_records.values()),
                    leaderboard=None,
                    composition_diagnostics=composition_diagnostics,
                    split_metadata=split_result.metadata,
                    split_metric_records=split_metric_records,
                    catalogs=catalogs,
                    chunk_diagnostics=chunk_diagnostics,
                    signal_diagnostics=signal_diagnostics,
                    portfolio_diagnostics=portfolio_diagnostics,
                ),
                error=error,
            )
            recorder.persist()
            raise
        chunk_record["status"] = "succeeded"
        chunk_record["stage"] = "completed"
        recorder.persist()

    leaderboard = build_split_leaderboard(
        split_metric_records,
        candidate_records,
        metric=config.ranking.metric,
        direction=config.ranking.direction,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    payload = _split_strategy_payload(
        config,
        data_result=data_result,
        array_contract=array_contract,
        strategy_evidence=strategy_evidence,
        indicator_evidence=indicator_evidence,
        candidates=list(candidate_records.values()),
        leaderboard=leaderboard,
        composition_diagnostics=composition_diagnostics,
        split_metadata=split_result.metadata,
        split_metric_records=split_metric_records,
        catalogs=catalogs,
        chunk_diagnostics=chunk_diagnostics,
        signal_diagnostics=signal_diagnostics,
        portfolio_diagnostics=portfolio_diagnostics,
    )
    _assert_split_leaderboard_complete(recorder, payload, leaderboard)
    _write_strategy_artifact(recorder, payload)
    recorder.mark_run_completed()
    return {
        **_run_refs(recorder),
        "lane": "run",
        "evidence_type": "strategy_sweep",
        "strategy_artifact_id": "strategy.run",
        "leaderboard": leaderboard,
    }


def _run_split_component_strategy_sweep(
    config: Any,
    *,
    component_registry: FrozenComponentRegistry,
    recorder: Any,
    data_result: Any,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    array_contract: DataArrayContract,
    indicator_contexts: list[IndicatorContext],
    composition_diagnostics: dict[str, Any],
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    close = data.feature("Close")
    split_result = build_run_splits_result(close.index, config.split)
    recorder.manifest.evidence["split"] = split_result.metadata
    split_execution_preflight = _split_execution_preflight(
        splits=split_result.splits,
        candidate_count=len(indicator_contexts),
        batch_size=config.candidate_grid.batch_size,
        symbol_count=len(close.columns),
        has_open_prices=open_prices is not None,
        max_estimated_cells=config.candidate_grid.max_estimated_cells,
    )
    composition_diagnostics["planned"]["split_execution_preflight"] = split_execution_preflight
    _assert_split_execution_budget(split_execution_preflight)
    _plan_strategy_artifact_if_needed(recorder)
    recorder.persist()
    definition = component_registry.get(ComponentSelection("strategies", config.strategy.id))
    strategy_callable = definition.load_callable()
    strategy_evidence = {
        "source": "component",
        "id": config.strategy.id,
        "version": definition.manifest.version,
        **definition.identity.public(),
    }
    candidate_records: dict[str, dict[str, Any]] = {}
    split_metric_records: list[dict[str, Any]] = []
    signal_diagnostics = _empty_signal_diagnostics()
    portfolio_diagnostics = _empty_portfolio_diagnostics()
    try:
        for context in indicator_contexts:
            inputs = _strategy_inputs_for_context(
                data=data,
                context=context,
                metadata={
                    "strategy_id": config.strategy.id,
                    "component_source_hash": definition.identity.source_hash,
                    "indicator_ids": [item["id"] for item in context.evidence],
                    "indicator_context_id": context.context_id,
                },
            )
            signal_result = validate_strategy_output(strategy_callable(inputs), inputs)
            _assert_strategy_consumed_indicator_context(inputs, strategy_id=config.strategy.id)
            strategy_candidate_id = config.strategy.id
            variant_id = _composed_candidate_id(
                strategy_source="component",
                strategy_id=config.strategy.id,
                strategy_candidate_id=strategy_candidate_id,
                indicator_candidates=context.candidate_evidence,
            )
            metric_records, split_portfolio_diagnostics = _split_metric_records_for_batch(
                close,
                open_prices,
                _candidate_signal_frame(signal_result.entries, variant_id),
                _candidate_signal_frame(signal_result.exits, variant_id),
                (variant_id,),
                split_result.splits,
                portfolio_config=config.portfolio,
                report_config=config.report,
            )
            split_metric_records.extend(metric_records)
            _record_context_composition(
                composition_diagnostics,
                context,
                strategy_candidate_count=1,
            )
            candidate_records[variant_id] = {
                "variant_id": variant_id,
                "composed_candidate_id": variant_id,
                "strategy_source": "component",
                "strategy_id": config.strategy.id,
                "strategy_candidate_id": strategy_candidate_id,
                "strategy_params": {},
                "component_source_hash": definition.identity.source_hash,
                "indicators": context.evidence,
                "indicator_candidates": context.candidate_evidence,
                "params": {},
                "metric_source": METRIC_SOURCE_CENTRAL_PORTFOLIO,
                "portfolio": to_builtin(asdict(config.portfolio)),
            }
            signal_diagnostics["candidates"][variant_id] = signal_result.diagnostics
            portfolio_diagnostics["candidates"][variant_id] = {
                "split_count": len(split_result.splits),
                "split_refs": [split.label for split in split_result.splits],
            }
            portfolio_diagnostics["chunks"][variant_id] = split_portfolio_diagnostics
    except Exception as error:
        _write_partial_split_strategy_artifact(
            recorder,
            _split_strategy_payload(
                config,
                data_result=data_result,
                array_contract=array_contract,
                strategy_evidence=strategy_evidence,
                indicator_evidence=[item for context in indicator_contexts for item in context.evidence],
                candidates=list(candidate_records.values()),
                leaderboard=None,
                composition_diagnostics=composition_diagnostics,
                split_metadata=split_result.metadata,
                split_metric_records=split_metric_records,
                signal_diagnostics=signal_diagnostics,
                portfolio_diagnostics=portfolio_diagnostics,
            ),
            error=error,
        )
        raise

    leaderboard = build_split_leaderboard(
        split_metric_records,
        candidate_records,
        metric=config.ranking.metric,
        direction=config.ranking.direction,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    payload = _split_strategy_payload(
        config,
        data_result=data_result,
        array_contract=array_contract,
        strategy_evidence=strategy_evidence,
        indicator_evidence=[item for context in indicator_contexts for item in context.evidence],
        candidates=list(candidate_records.values()),
        leaderboard=leaderboard,
        composition_diagnostics=composition_diagnostics,
        split_metadata=split_result.metadata,
        split_metric_records=split_metric_records,
        signal_diagnostics=signal_diagnostics,
        portfolio_diagnostics=portfolio_diagnostics,
    )
    _assert_split_leaderboard_complete(recorder, payload, leaderboard)
    _write_strategy_artifact(recorder, payload)
    recorder.mark_run_completed()
    return {
        **_run_refs(recorder),
        "lane": "run",
        "evidence_type": "strategy_sweep",
        "strategy_artifact_id": "strategy.run",
        "leaderboard": leaderboard,
    }


def _candidate_signal_frame(frame: pd.DataFrame, candidate_id: str) -> pd.DataFrame:
    result = frame.copy()
    result.columns = pd.MultiIndex.from_product(
        [[candidate_id], list(frame.columns)],
        names=[CANDIDATE_LEVEL, SYMBOL_LEVEL],
    )
    return result


def _split_metric_records_for_batch(
    close: pd.DataFrame,
    open_prices: pd.DataFrame | None,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    candidate_ids: tuple[str, ...],
    splits: list[RunSplit],
    *,
    portfolio_config: Any,
    report_config: Any,
    roles: tuple[str, ...] = ("selection", "held_out"),
    candidate_ids_by_split: Mapping[str, set[str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {
        "schema_version": "split_portfolio_diagnostics.v1",
        "splits": {},
    }
    for split in splits:
        split_diagnostics = diagnostics["splits"].setdefault(split.label, {})
        for role, native_set, window_index in (
            ("selection", split.selection_set, split.selection_index),
            ("held_out", split.held_out_set, split.held_out_index),
        ):
            if role not in roles:
                continue
            window_close = close.loc[window_index]
            window_open = open_prices.loc[window_index] if open_prices is not None else None
            portfolio = simulate_portfolio_batch(
                window_close,
                entries.loc[window_index],
                exits.loc[window_index],
                portfolio_config,
                SignalConfig(),
                open_prices=window_open,
                market_index=close.index,
            )
            split_diagnostics[role] = to_builtin(portfolio.diagnostics)
            metrics_by_candidate = portfolio_metrics_by_candidate_group(
                portfolio.portfolio,
                report_config,
                candidate_ids,
            )
            for candidate_id in candidate_ids:
                if candidate_ids_by_split is not None and candidate_id not in candidate_ids_by_split.get(
                    split.label,
                    set(),
                ):
                    continue
                records.append(
                    {
                        "schema_version": "split_metric.v1",
                        "split_label": split.label,
                        "split": split.label,
                        "set": role,
                        "native_set": native_set,
                        "candidate_id": candidate_id,
                        "row_count": len(window_index),
                        "metric_source": METRIC_SOURCE_CENTRAL_PORTFOLIO,
                        "metrics": metrics_by_candidate[candidate_id],
                    }
                )
    return records, diagnostics


def _merge_split_portfolio_diagnostics(target: dict[str, Any], source: dict[str, Any]) -> None:
    target.setdefault("schema_version", source.get("schema_version"))
    target_splits = target.setdefault("splits", {})
    for split_label, split_diagnostics in source.get("splits", {}).items():
        target_splits.setdefault(split_label, {}).update(split_diagnostics)


def _selected_candidate_ids_by_split(
    records: list[dict[str, Any]],
    *,
    metric: str,
    direction: str,
) -> dict[str, set[str]]:
    selected: dict[str, dict[str, Any]] = {}
    reverse = direction == "desc"
    for record in records:
        if record.get("set") != "selection" or "candidate_id" not in record:
            continue
        value = _split_metric_value(record, metric)
        if value is None:
            continue
        split_label = str(record["split_label"])
        current = selected.get(split_label)
        if current is None:
            selected[split_label] = record
            continue
        current_value = _split_metric_value(current, metric)
        if current_value is None:
            selected[split_label] = record
            continue
        key = (value, str(record["candidate_id"]))
        current_key = (current_value, str(current["candidate_id"]))
        if (key > current_key) if reverse else (key < current_key):
            selected[split_label] = record
    return {
        split_label: {str(record["candidate_id"])} for split_label, record in selected.items()
    }


def _split_metric_value(record: Mapping[str, Any], metric: str) -> float | None:
    metrics = record.get("metrics", {})
    value = metrics.get(metric) if isinstance(metrics, Mapping) else None
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _split_execution_preflight(
    *,
    splits: list[RunSplit],
    candidate_count: int,
    batch_size: int,
    symbol_count: int,
    has_open_prices: bool,
    max_estimated_cells: int,
) -> dict[str, Any]:
    batch_candidate_count = min(candidate_count, batch_size)
    selection_rows = sum(len(split.selection_index) for split in splits)
    held_out_rows = sum(len(split.held_out_index) for split in splits)
    total_window_rows = selection_rows + held_out_rows
    materialized_frame_count = 4 + int(has_open_prices)
    estimated_cells = batch_candidate_count * total_window_rows * symbol_count * materialized_frame_count
    return {
        "schema_version": "split_execution_preflight.v1",
        "split_count": len(splits),
        "candidate_count": candidate_count,
        "batch_candidate_count": batch_candidate_count,
        "batch_size": batch_size,
        "selection_rows": selection_rows,
        "held_out_rows": held_out_rows,
        "total_window_rows": total_window_rows,
        "symbol_count": symbol_count,
        "materialized_frame_count": materialized_frame_count,
        "estimated_cells": estimated_cells,
        "limits": {"max_estimated_cells": max_estimated_cells},
    }


def _assert_split_execution_budget(preflight: dict[str, Any]) -> None:
    estimated_cells = int(preflight["estimated_cells"])
    max_estimated_cells = int(preflight["limits"]["max_estimated_cells"])
    if estimated_cells > max_estimated_cells:
        raise CandidateSweepError(
            f"split strategy execution batch has {estimated_cells} estimated cells, above "
            f"candidate_grid.max_estimated_cells={max_estimated_cells}; reduce "
            "candidate_grid.batch_size or split workload"
        )


def _split_strategy_payload(
    config: Any,
    *,
    data_result: Any,
    array_contract: DataArrayContract,
    strategy_evidence: dict[str, Any],
    indicator_evidence: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    leaderboard: dict[str, Any] | None,
    composition_diagnostics: dict[str, Any],
    split_metadata: dict[str, Any],
    split_metric_records: list[dict[str, Any]],
    signal_diagnostics: dict[str, Any],
    portfolio_diagnostics: dict[str, Any],
    catalogs: dict[str, Any] | None = None,
    chunk_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": STRATEGY_ARTIFACT_SCHEMA_VERSION,
        "lane": "run",
        "evidence_type": "strategy_sweep",
        "strategy": strategy_evidence,
        "indicators": indicator_evidence,
        "data": _strategy_data_evidence_payload(
            data_result,
            array_contract,
            strategy_source=config.strategy.source,
        ),
        "split": split_metadata,
        "candidates": [to_builtin(record) for record in candidates],
        "leaderboard": leaderboard or _partial_split_leaderboard(config),
        "split_metrics": to_builtin(split_metric_records),
        "split_diagnostics": _split_diagnostics(split_metadata, split_metric_records),
        "composition": composition_diagnostics,
        "signal_diagnostics": signal_diagnostics,
        "portfolio_diagnostics": portfolio_diagnostics,
    }
    if catalogs is not None:
        payload["catalogs"] = catalogs
    if chunk_diagnostics is not None:
        payload["chunk_diagnostics"] = chunk_diagnostics
    return payload


def _partial_split_leaderboard(config: Any) -> dict[str, Any]:
    return {
        "schema_version": "split_run_leaderboard.v1",
        "primary_metric": config.ranking.metric,
        "direction": config.ranking.direction,
        "weight_basis": "held_out_row_count",
        "rows": [],
        "failure_samples": [],
        "summary": {
            "attempted_splits": 0,
            "selected_splits": 0,
            "candidate_count": 0,
            "partial_leaderboard": True,
            "failure_gating_status": "partial",
        },
    }


def _split_diagnostics(
    split_metadata: dict[str, Any],
    split_metric_records: list[dict[str, Any]],
) -> dict[str, Any]:
    selection_metric_counts: dict[str, int] = {}
    for row in split_metric_records:
        if row.get("set") != "selection":
            continue
        candidate_id = str(row["candidate_id"])
        selection_metric_counts[candidate_id] = selection_metric_counts.get(candidate_id, 0) + 1
    return {
        "schema_version": "split_strategy_diagnostics.v1",
        "split_count": split_metadata.get("n_splits", 0),
        "metric_record_count": len(split_metric_records),
        "selection_metric_record_count": sum(
            1 for record in split_metric_records if record.get("set") == "selection"
        ),
        "held_out_metric_record_count": sum(
            1 for record in split_metric_records if record.get("set") == "held_out"
        ),
        "candidate_selection_metric_counts": selection_metric_counts,
    }


def _assert_split_leaderboard_complete(
    recorder: Any,
    payload: dict[str, Any],
    leaderboard: dict[str, Any],
) -> None:
    summary = leaderboard.get("summary", {})
    if leaderboard.get("rows") and not summary.get("partial_leaderboard"):
        return
    error = RuntimeError(
        "split strategy sweep did not produce a complete leaderboard: "
        f"selected_splits={summary.get('selected_splits', 0)}, "
        f"attempted_splits={summary.get('attempted_splits', 0)}, "
        f"partial={summary.get('partial_leaderboard', True)}"
    )
    _write_partial_split_strategy_artifact(recorder, payload, error=error)
    raise error


def _write_partial_split_strategy_artifact(
    recorder: Any,
    payload: dict[str, Any],
    *,
    error: Exception,
) -> None:
    _plan_strategy_artifact_if_needed(recorder)
    recorder.artifacts.begin_artifact_write("strategy.run")
    artifact_path = Path("strategy_run.json")
    full_path = recorder.run_dir / artifact_path
    atomic_write_json(full_path, payload)
    artifact = _strategy_artifact_record(recorder)
    if artifact is None:
        raise RuntimeError("strategy.run artifact disappeared during partial write")
    recorder.manifest.replace_artifact(
        "strategy.run",
        {
            **artifact,
            "hash": hash_file(full_path),
            "size": full_path.stat().st_size,
            "shape": _strategy_artifact_shape(payload),
            "status": ArtifactStatus.PARTIAL,
            "diagnostic": {
                "error_type": type(error).__name__,
                "message": str(error)[:1000],
            },
        },
    )
    recorder.persist()


def _resolve_sweep_indicator_refs(
    refs: list[RunIndicatorSourceConfig],
    *,
    component_registry: FrozenComponentRegistry,
    playbook_registry: FrozenPlaybookRegistry,
    data: MarketDataBundle,
    candidate_grid: Any,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[CandidateAxis],
    dict[tuple[str, str, str], dict[str, Any]],
    dict[str, Any],
]:
    indicators: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []
    axes: list[CandidateAxis] = []
    sweep_results: list[IndicatorSweepResult] = []
    candidate_evidence: dict[tuple[str, str, str], dict[str, Any]] = {}
    seen_playbook_ids: set[str] = set()
    for ref in refs:
        if ref.source == "component":
            component_ids = ref.expanded_ids(component_registry.ids("indicators"))
            for component_id in component_ids:
                if component_id in indicators:
                    raise ValueError(f"duplicate indicator component ref: {component_id}")
                output, source_evidence = _load_component_indicator_ref(
                    component_id,
                    component_registry=component_registry,
                    data=data,
                )
                indicators[component_id] = output
                evidence.append(source_evidence)
            continue

        playbook_ids = ref.expanded_ids(playbook_registry.ids("indicators"))
        for playbook_id in playbook_ids:
            if playbook_id in seen_playbook_ids:
                raise ValueError(f"duplicate indicator playbook ref: {playbook_id}")
            seen_playbook_ids.add(playbook_id)
            definition = playbook_registry.get(PlaybookSelection("indicators", playbook_id))
            if definition.manifest.result_schema != PLAYBOOK_SWEEP_RESULT_SCHEMA:
                raise ValueError(
                    f"strategy sweep run requires indicator playbook {definition.id!r} "
                    f"to use result_schema {PLAYBOOK_SWEEP_RESULT_SCHEMA!r}"
                )
            result = validate_indicator_sweep_result(
                definition.load_callable()(data),
                source_id=definition.id,
                close=data.feature("Close"),
            )
            source_key = _indicator_source_key(definition.id)
            source_evidence = {
                "source": "playbook",
                "id": definition.id,
                "version": definition.manifest.version,
                **definition.identity.public(),
                "indicator_family": definition.manifest.indicator_family,
                "baseline_component_indicator_id": definition.manifest.baseline_component_indicator_id,
                "candidate_count": result.axis.count,
                "result_contract": PLAYBOOK_SWEEP_CONTRACT,
            }
            indicators[source_key] = {
                "candidate_axis": [
                    {"candidate_id": candidate.candidate_id, "params": to_builtin(candidate.params)}
                    for candidate in result.axis.candidates
                ],
                "outputs": result.outputs,
                "diagnostics": result.diagnostics,
            }
            for candidate in result.axis.candidates:
                candidate_evidence[("playbook", definition.id, candidate.candidate_id)] = (
                    source_evidence
                    | {
                        "candidate_id": candidate.candidate_id,
                        "params": to_builtin(candidate.params),
                        "outputs": sorted(result.outputs),
                        "source_key": source_key,
                    }
                )
            axes.append(result.axis)
            sweep_results.append(result)
            evidence.append(source_evidence)
    preflight = preflight_indicator_grid(
        sweep_results,
        max_candidates=candidate_grid.max_candidates,
        max_estimated_cells=candidate_grid.max_estimated_cells,
    ).diagnostics()
    return indicators, evidence, axes, candidate_evidence, preflight


def _load_component_indicator_ref(
    component_id: str,
    *,
    component_registry: FrozenComponentRegistry,
    data: MarketDataBundle,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    definition = component_registry.get(ComponentSelection("indicators", component_id))
    output = definition.load_callable()(data)
    return (
        _validate_indicator_output(
            output,
            data.feature("Close"),
            component_id,
        ),
        {
            "source": "component",
            "id": component_id,
            "version": definition.manifest.version,
            **definition.identity.public(),
        },
    )


def _sweep_artifact_catalogs(
    *,
    strategy_evidence: dict[str, Any],
    indicator_evidence: list[dict[str, Any]],
    indicator_candidate_evidence: dict[tuple[str, str, str], dict[str, Any]],
    strategy_axis: CandidateAxis,
    composed_candidates: tuple[ComposedCandidate, ...],
) -> dict[str, Any]:
    catalogs: dict[str, Any] = {
        "schema_version": "strategy_sweep_catalogs.v1",
        "sources": {
            _strategy_source_ref(strategy_evidence["source"], strategy_evidence["id"]): to_builtin(
                strategy_evidence
            ),
        },
        "indicator_candidates": {},
        "strategy_candidates": {},
        "composed_candidates": {},
        "chunks": {},
        "metrics": {},
    }
    for evidence in indicator_evidence:
        catalogs["sources"][_indicator_source_ref(evidence["source"], evidence["id"])] = to_builtin(
            evidence
        )
    for (source, source_id, candidate_id), evidence in indicator_candidate_evidence.items():
        catalogs["indicator_candidates"][_indicator_candidate_ref_parts(source, source_id, candidate_id)] = (
            to_builtin(evidence)
        )
    for candidate in strategy_axis.candidates:
        catalogs["strategy_candidates"][
            _strategy_candidate_ref_parts(strategy_axis.source, strategy_axis.source_id, candidate.candidate_id)
        ] = {
            "source_ref": _strategy_source_ref(strategy_axis.source, strategy_axis.source_id),
            "source": strategy_axis.source,
            "id": strategy_axis.source_id,
            "candidate_id": candidate.candidate_id,
            "params": to_builtin(candidate.params),
        }
    for candidate in composed_candidates:
        catalogs["composed_candidates"][candidate.candidate_id] = {
            "candidate_id": candidate.candidate_id,
            "strategy_candidate_ref": _strategy_candidate_ref(candidate.strategy),
            "indicator_candidate_refs": [
                _indicator_candidate_ref(indicator) for indicator in candidate.indicators
            ],
        }
    return catalogs


def _compact_sweep_candidate_records(catalogs: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "variant_id": candidate_id,
            "composed_candidate_id": candidate_id,
            "strategy_candidate_ref": record["strategy_candidate_ref"],
            "indicator_candidate_refs": record["indicator_candidate_refs"],
            "metric_ref": record["metric_ref"],
            "chunk_ref": record["chunk_ref"],
            "metric_source": METRIC_SOURCE_CENTRAL_PORTFOLIO,
        }
        for candidate_id, record in catalogs["composed_candidates"].items()
    ]


def _strategy_source_ref(source: str, source_id: str) -> str:
    return f"strategy:{source}:{source_id}"


def _indicator_source_ref(source: str, source_id: str) -> str:
    return f"indicator:{source}:{source_id}"


def _strategy_candidate_ref(candidate: Any) -> str:
    return _strategy_candidate_ref_parts(candidate.source, candidate.source_id, candidate.candidate_id)


def _strategy_candidate_ref_parts(source: str, source_id: str, candidate_id: str) -> str:
    return f"strategy:{source}:{source_id}:{candidate_id}"


def _indicator_candidate_ref(candidate: Any) -> str:
    return _indicator_candidate_ref_parts(candidate.source, candidate.source_id, candidate.candidate_id)


def _indicator_candidate_ref_parts(source: str, source_id: str, candidate_id: str) -> str:
    return f"indicator:{source}:{source_id}:{candidate_id}"


def _assert_sweep_candidate_budget(
    candidate_count: int,
    max_candidates: int,
) -> None:
    if candidate_count > max_candidates:
        raise CandidateSweepError(
            f"strategy sweep composed grid has {candidate_count} candidates, above "
            f"candidate_grid.max_candidates={max_candidates}"
        )


def _sweep_execution_preflight(
    *,
    total_composed_candidates: int,
    batch_size: int,
    row_count: int,
    symbol_count: int,
    has_open_prices: bool,
    max_estimated_cells: int,
) -> dict[str, Any]:
    batch_candidate_count = min(total_composed_candidates, batch_size)
    materialized_frame_count = 4 + int(has_open_prices)
    estimated_cells = batch_candidate_count * row_count * symbol_count * materialized_frame_count
    return {
        "schema_version": "strategy_sweep_execution_preflight.v1",
        "batch_candidate_count": batch_candidate_count,
        "row_count": row_count,
        "symbol_count": symbol_count,
        "materialized_frame_count": materialized_frame_count,
        "estimated_cells": estimated_cells,
        "limits": {"max_estimated_cells": max_estimated_cells},
    }


def _assert_sweep_execution_budget(preflight: dict[str, Any]) -> None:
    estimated_cells = int(preflight["estimated_cells"])
    max_estimated_cells = int(preflight["limits"]["max_estimated_cells"])
    if estimated_cells > max_estimated_cells:
        raise CandidateSweepError(
            f"strategy sweep execution batch has {estimated_cells} estimated cells, above "
            f"candidate_grid.max_estimated_cells={max_estimated_cells}; reduce "
            "candidate_grid.batch_size"
        )


def _candidate_batches(
    candidates: tuple[ComposedCandidate, ...],
    batch_size: int,
) -> Iterator[tuple[ComposedCandidate, ...]]:
    for start in range(0, len(candidates), batch_size):
        yield candidates[start : start + batch_size]


def _candidate_batch_count(
    candidate_count: int,
    batch_size: int,
) -> int:
    return (candidate_count + batch_size - 1) // batch_size


def _sweep_composed_candidate_count(
    strategy_axis: CandidateAxis,
    indicator_axes: list[CandidateAxis],
) -> int:
    count = strategy_axis.count
    for axis in indicator_axes:
        count *= axis.count
    return count


def _persist_sweep_preflight_failure(recorder: Any, error: CandidateSweepError) -> None:
    if error.diagnostics is None:
        return
    recorder.manifest.evidence["composition"] = {"indicator_preflight": error.diagnostics}
    recorder.persist()


def _empty_chunk_diagnostics() -> dict[str, Any]:
    return {
        "schema_version": "strategy_sweep_chunk_diagnostics.v1",
        "chunks": [],
    }


def _sweep_chunk_ref(batch_index: int) -> str:
    return f"batch-{batch_index:06d}"


def _sweep_chunk_record(
    batch_index: int,
    candidate_ids: tuple[str, ...],
    chunk_ref: str,
) -> dict[str, Any]:
    return {
        "chunk_ref": chunk_ref,
        "batch_index": batch_index,
        "candidate_count": len(candidate_ids),
        "candidate_ids": list(candidate_ids),
        "status": "running",
        "stage": "planned",
    }


def _mark_sweep_chunk_failed(chunk_record: dict[str, Any], error: Exception) -> None:
    chunk_record["status"] = "failed"
    chunk_record["error"] = {
        "stage": chunk_record["stage"],
        "error_type": type(error).__name__,
        "message": str(error)[:1000],
    }


def _fixed_indicator_contexts(
    fixed_indicators: dict[str, Any],
    fixed_evidence: list[dict[str, Any]],
) -> list[IndicatorContext]:
    return [
        IndicatorContext(
            context_id="fixed-indicators",
            indicators=dict(fixed_indicators),
            evidence=list(fixed_evidence),
            candidate_evidence=[],
            required_indicator_keys=(),
        )
    ]


def _composition_diagnostics() -> dict[str, Any]:
    return {
        "schema_version": "strategy_composition.v1",
        "planned": {
            "indicator_axes": [],
            "indicator_context_count": 1,
        },
        "strategy_contexts": {},
        "total_composed_candidates": 0,
    }


def _indicator_source_key(source_id: str) -> str:
    return f"playbook:{source_id}"


def _strategy_data_array_contract(
    config: Any,
    component_registry: FrozenComponentRegistry,
    playbook_registry: FrozenPlaybookRegistry,
) -> DataArrayContract:
    return build_data_array_contract(
        configured_arrays=config.data.effective_arrays,
        component_required_arrays=_strategy_required_arrays(
            config,
            component_registry,
            playbook_registry,
        ),
        pipeline_required_arrays=("Close", "Open"),
    )


def _strategy_required_arrays(
    config: Any,
    component_registry: FrozenComponentRegistry,
    playbook_registry: FrozenPlaybookRegistry,
) -> tuple[str, ...]:
    required: list[tuple[str, ...]] = []
    if config.strategy.source == "component":
        required.append(
            component_registry.get(ComponentSelection("strategies", config.strategy.id)).input_names
        )
    if config.strategy.source == "playbook":
        required.append(
            playbook_registry.get(PlaybookSelection("strategies", config.strategy.id)).input_names
        )
    for ref in config.indicators:
        if ref.source == "component":
            for component_id in ref.expanded_ids(component_registry.ids("indicators")):
                required.append(
                    component_registry.get(
                        ComponentSelection("indicators", component_id)
                    ).input_names
                )
            continue
        for playbook_id in ref.expanded_ids(playbook_registry.ids("indicators")):
            required.append(
                playbook_registry.get(PlaybookSelection("indicators", playbook_id)).input_names
            )
    return merge_data_arrays(*required)


def _resolve_strategy_ref(
    ref: RunSourceRefConfig,
    *,
    component_registry: FrozenComponentRegistry,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    indicator_contexts: list[IndicatorContext],
    portfolio_config: Any,
    report_config: Any,
    composition_diagnostics: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    definition = component_registry.get(ComponentSelection("strategies", ref.id))
    strategy_callable = definition.load_callable()
    records = []
    signal_diagnostics = _empty_signal_diagnostics()
    portfolio_diagnostics = _empty_portfolio_diagnostics()
    for context in indicator_contexts:
        inputs = _strategy_inputs_for_context(
            data=data,
            context=context,
            metadata={
                "strategy_id": ref.id,
                "component_source_hash": definition.identity.source_hash,
                "indicator_ids": [item["id"] for item in context.evidence],
                "indicator_context_id": context.context_id,
            },
        )
        output = strategy_callable(inputs)
        _assert_strategy_consumed_indicator_context(inputs, strategy_id=ref.id)
        strategy_candidate_id = ref.id
        variant_id = _composed_candidate_id(
            strategy_source="component",
            strategy_id=ref.id,
            strategy_candidate_id=strategy_candidate_id,
            indicator_candidates=context.candidate_evidence,
        )
        record, signal_diagnostic, portfolio_diagnostic = _score_strategy_signals(
            validate_strategy_output(output, inputs),
            data=data,
            open_prices=open_prices,
            portfolio_config=portfolio_config,
            report_config=report_config,
            variant_id=variant_id,
            params={},
            source_fields={
                "composed_candidate_id": variant_id,
                "strategy_source": "component",
                "strategy_id": ref.id,
                "strategy_candidate_id": strategy_candidate_id,
                "strategy_params": {},
                "component_source_hash": definition.identity.source_hash,
                "indicators": context.evidence,
                "indicator_candidates": context.candidate_evidence,
            },
        )
        _record_context_composition(
            composition_diagnostics,
            context,
            strategy_candidate_count=1,
        )
        records.append(record)
        signal_diagnostics["candidates"][variant_id] = signal_diagnostic
        portfolio_diagnostics["candidates"][variant_id] = portfolio_diagnostic
    return (
        {
            "source": "component",
            "id": ref.id,
            "version": definition.manifest.version,
            **definition.identity.public(),
        },
        records,
        signal_diagnostics,
        portfolio_diagnostics,
    )


def _strategy_inputs_for_context(
    *,
    data: MarketDataBundle,
    context: IndicatorContext,
    metadata: dict[str, Any],
) -> StrategyInputs:
    return StrategyInputs(
        data=data,
        indicators=StrategyIndicatorInputs(
            _isolated_indicator_values(context.indicators),
            required_consumed_keys=context.required_indicator_keys,
        ),
        metadata=metadata,
    )


def _isolated_indicator_values(indicators: Mapping[str, Any]) -> dict[str, Any]:
    isolated: dict[str, Any] = {}
    for key, value in indicators.items():
        if isinstance(value, Mapping) and isinstance(value.get("outputs"), Mapping):
            isolated[key] = {
                **value,
                "outputs": {
                    output_name: output.copy() if isinstance(output, pd.DataFrame) else output
                    for output_name, output in value["outputs"].items()
                },
            }
            continue
        isolated[key] = value
    return isolated


def _assert_strategy_consumed_indicator_context(
    inputs: StrategyInputs,
    *,
    strategy_id: str,
) -> None:
    indicators = inputs.indicators
    if not isinstance(indicators, StrategyIndicatorInputs):
        raise TypeError("strategy indicator inputs must be StrategyIndicatorInputs")
    missing = indicators.missing_required_keys
    if missing:
        raise ValueError(
            f"strategy {strategy_id!r} did not consume selected indicator playbook axes: "
            f"{list(missing)}"
        )


def _empty_signal_diagnostics() -> dict[str, Any]:
    return {
        "schema_version": "strategy_signal_candidate_diagnostics.v1",
        "candidates": {},
    }


def _empty_portfolio_diagnostics() -> dict[str, Any]:
    return {
        "schema_version": "strategy_portfolio_candidate_diagnostics.v2",
        "candidates": {},
        "chunks": {},
    }


def _record_context_composition(
    diagnostics: dict[str, Any],
    context: IndicatorContext,
    *,
    strategy_candidate_count: int,
) -> None:
    contexts = diagnostics.setdefault("strategy_contexts", {})
    contexts[context.context_id] = {
        "indicator_candidates": context.candidate_evidence,
        "strategy_candidate_count": strategy_candidate_count,
    }
    diagnostics["total_composed_candidates"] = int(
        diagnostics.get("total_composed_candidates", 0)
    ) + strategy_candidate_count


def _composed_candidate_id(
    *,
    strategy_source: str,
    strategy_id: str,
    strategy_candidate_id: str,
    indicator_candidates: list[dict[str, Any]],
) -> str:
    if not indicator_candidates:
        return strategy_candidate_id
    indicator_tokens = [
        f"{item['source']}:{item['id']}:{item['candidate_id']}"
        for item in indicator_candidates
    ]
    return (
        f"strategy:{strategy_source}:{strategy_id}:{strategy_candidate_id}"
        f"+indicators:[{','.join(indicator_tokens)}]"
    )


def _assert_unique_strategy_variant_ids(records: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records):
        variant_id = record.get("variant_id")
        if not isinstance(variant_id, str) or not variant_id:
            raise TypeError(f"strategy candidate record {index} must include a non-empty variant_id")
        if variant_id in seen:
            raise ValueError(f"duplicate composed strategy candidate id: {variant_id}")
        seen.add(variant_id)


def _score_strategy_signals(
    signal_result: StrategySignalResult,
    *,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    portfolio_config: Any,
    report_config: Any,
    variant_id: str,
    params: Mapping[str, Any],
    source_fields: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    close = data.feature("Close")
    portfolio = simulate_portfolio(
        close,
        signal_result.entries,
        signal_result.exits,
        portfolio_config,
        SignalConfig(),
        open_prices=open_prices,
        market_index=close.index,
    )
    return (
        {
            "variant_id": variant_id,
            **source_fields,
            "params": to_builtin(dict(params)),
            "metrics": portfolio_metrics(portfolio.portfolio, report_config),
            "metric_source": METRIC_SOURCE_CENTRAL_PORTFOLIO,
            "portfolio": to_builtin(asdict(portfolio_config)),
        },
        signal_result.diagnostics,
        portfolio.diagnostics,
    )


def _validate_indicator_output(output: Any, close: pd.DataFrame, component_id: str) -> Any:
    frame = output.to_frame() if isinstance(output, pd.Series) else output
    if isinstance(frame, pd.DataFrame):
        _assert_indicator_frame(frame, close, component_id)
        return frame
    result_frame = getattr(output, "frame", None)
    if isinstance(result_frame, pd.DataFrame):
        _assert_indicator_frame(result_frame, close, component_id)
        return output
    raise TypeError(
        f"indicator component {component_id!r} must return a pandas object or IndicatorResult"
    )


def _assert_indicator_frame(frame: pd.DataFrame, close: pd.DataFrame, component_id: str) -> None:
    if not frame.index.equals(close.index):
        raise ValueError(f"indicator source {component_id!r} has misaligned timestamps")
    if list(map(str, frame.columns)) != list(map(str, close.columns)):
        raise ValueError(f"indicator source {component_id!r} has misaligned symbols")


def _strategy_data_evidence_payload(
    data_result: Any,
    array_contract: DataArrayContract,
    *,
    strategy_source: str,
) -> dict[str, Any]:
    payload = data_array_evidence_payload(data_result, array_contract)
    if strategy_source == "playbook":
        payload |= {
            "strategy_consumed_runner_data": True,
            "strategy_data_binding": "strategy_sweep_inputs",
        }
    else:
        payload |= {
            "strategy_consumed_runner_data": True,
            "strategy_data_binding": "runner_data_bundle",
        }
    return payload


def _assert_leaderboard_complete(leaderboard: dict[str, Any]) -> None:
    summary = leaderboard.get("summary", {})
    failed = int(summary.get("failed", 0))
    excluded = int(summary.get("excluded", 0))
    succeeded = int(summary.get("succeeded", 0))
    if failed or excluded or not succeeded:
        raise RuntimeError(
            "strategy sweep did not produce a complete leaderboard: "
            f"succeeded={succeeded}, failed={failed}, excluded={excluded}"
        )


def _run_refs(recorder) -> dict[str, Any]:
    return {
        "run_id": recorder.manifest.run_id,
        "run_dir": str(recorder.run_dir),
        "manifest_path": str(recorder.manifest_path),
        "status": recorder.manifest.status,
        "started_at": recorder.manifest.started_at,
        "finished_at": recorder.manifest.finished_at,
    }


def validate_strategy_output(output: Any, inputs: StrategyInputs) -> StrategySignalResult:
    if not isinstance(output, dict):
        raise TypeError("strategy output must be a mapping")
    forbidden = sorted(set(output) & STRATEGY_OUTPUT_FORBIDDEN_KEYS)
    if forbidden:
        raise ValueError(f"strategy output must not contain portfolio fields: {forbidden}")
    if "entries" not in output or "exits" not in output:
        raise ValueError("strategy output must include entries and exits")
    close = inputs.data.feature("Close")
    entries = _signal_frame(output["entries"], close, "entries")
    exits = _signal_frame(output["exits"], close, "exits")
    diagnostics = {
        "schema_version": "strategy_signal_diagnostics.v1",
        "entry_states": _true_count(entries),
        "exit_states": _true_count(exits),
        "symbols": [str(column) for column in entries.columns],
        "timing": "signals_are_bar_aligned_inputs_to_config_owned_portfolio_execution",
    }
    if isinstance(inputs.indicators, StrategyIndicatorInputs):
        diagnostics["consumed_indicator_keys"] = list(inputs.indicators.consumed_keys)
    if isinstance(output.get("diagnostics"), dict):
        diagnostics["strategy"] = output["diagnostics"]
    return StrategySignalResult(entries=entries, exits=exits, diagnostics=diagnostics)


def _signal_frame(value: Any, close: pd.DataFrame, name: str) -> pd.DataFrame:
    frame = value.to_frame() if isinstance(value, pd.Series) else value
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"strategy output {name} must be a pandas DataFrame")
    if not frame.index.equals(close.index):
        raise ValueError(f"strategy output {name} has misaligned timestamps")
    if list(map(str, frame.columns)) != list(map(str, close.columns)):
        raise ValueError(f"strategy output {name} has misaligned symbols")
    return frame.fillna(False).astype(bool)


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
    if "split_metrics" in payload:
        shape["split_metric_count"] = len(payload.get("split_metrics", []))
    catalogs = payload.get("catalogs")
    if isinstance(catalogs, Mapping):
        shape |= {
            "source_count": len(catalogs.get("sources", {})),
            "indicator_candidate_count": len(catalogs.get("indicator_candidates", {})),
            "strategy_candidate_count": len(catalogs.get("strategy_candidates", {})),
            "composed_candidate_count": len(catalogs.get("composed_candidates", {})),
            "chunk_count": len(catalogs.get("chunks", {})),
            "metric_count": len(catalogs.get("metrics", {})),
        }
    return shape


def _true_count(value: pd.DataFrame | pd.Series) -> int:
    return int(value.to_numpy(dtype=bool).sum())
