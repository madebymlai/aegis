from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd

from research.aegis_research.batched_candidates import reject_batched_result_in_record_runner
from research.aegis_research.component_registry import (
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.component_registry.manifests import COMPONENT_ID_RE
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
from research.aegis_research.portfolios import simulate_portfolio
from research.aegis_research.provenance.experiment_artifacts import ExperimentArtifactWriter
from research.aegis_research.provenance.manifest import atomic_write_json, hash_file
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.provenance.run_store import RunStore
from research.aegis_research.reports import portfolio_metrics
from research.aegis_research.run_leaderboard import (
    METRIC_SOURCE_CENTRAL_PORTFOLIO,
    build_run_leaderboard,
)

STRATEGY_ARTIFACT_SCHEMA_VERSION = "strategy_run.v2"
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
class IndicatorPlaybookCandidate:
    source_key: str
    source_id: str
    candidate_id: str
    params: dict[str, Any]
    outputs: dict[str, pd.DataFrame]
    evidence: dict[str, Any]


@dataclass(frozen=True)
class IndicatorPlaybookAxis:
    source_key: str
    source_id: str
    candidates: tuple[IndicatorPlaybookCandidate, ...]


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
        indicators, indicator_evidence, indicator_axes = _resolve_indicator_refs(
            config.indicators,
            component_registry=component_registry,
            playbook_registry=playbooks,
            data=data_bundle,
        )
        composition_diagnostics = _composition_diagnostics(indicator_axes)
        recorder.manifest.evidence["composition"] = composition_diagnostics["planned"]
        recorder.persist()
        indicator_contexts = _indicator_contexts(indicators, indicator_evidence, indicator_axes)

        strategy_evidence, strategy_variant_records, signal_diagnostics, portfolio_diagnostics = (
            _resolve_strategy_ref(
                config.strategy,
                component_registry=component_registry,
                playbook_registry=playbooks,
                data=data_bundle,
                open_prices=open_prices,
                indicator_contexts=indicator_contexts,
                portfolio_config=config.portfolio,
                report_config=config.report,
                composition_diagnostics=composition_diagnostics,
            )
        )
        _assert_unique_strategy_variant_ids(strategy_variant_records)
        leaderboard = build_run_leaderboard(
            strategy_variant_records,
            metric=config.ranking.metric,
            direction=config.ranking.direction,
            rank_by=config.ranking.rank_by,
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
            "candidates": [to_builtin(record) for record in strategy_variant_records],
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
    playbook_registry: FrozenPlaybookRegistry,
    data: MarketDataBundle,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[IndicatorPlaybookAxis]]:
    indicators: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []
    axes: list[IndicatorPlaybookAxis] = []
    seen_playbook_ids: set[str] = set()
    for ref in refs:
        if ref.source == "component":
            component_ids = ref.expanded_ids(component_registry.ids("indicators"))
            for component_id in component_ids:
                if component_id in indicators:
                    raise ValueError(f"duplicate indicator component ref: {component_id}")
                definition = component_registry.get(ComponentSelection("indicators", component_id))
                output = definition.load_callable()(data)
                indicators[component_id] = _validate_indicator_output(
                    output,
                    data.feature("Close"),
                    component_id,
                )
                evidence.append(
                    {
                        "source": "component",
                        "id": component_id,
                        "version": definition.manifest.version,
                        **definition.identity.public(),
                    }
                )
            continue

        playbook_ids = ref.expanded_ids(playbook_registry.ids("indicators"))
        for playbook_id in playbook_ids:
            if playbook_id in seen_playbook_ids:
                raise ValueError(f"duplicate indicator playbook ref: {playbook_id}")
            seen_playbook_ids.add(playbook_id)
            definition = playbook_registry.get(PlaybookSelection("indicators", playbook_id))
            result = definition.load_callable()(data)
            reject_batched_result_in_record_runner(result, source_id=definition.id)
            _reject_playbook_metric_records(result, source_id=definition.id)
            source_evidence = {
                "source": "playbook",
                "id": definition.id,
                "version": definition.manifest.version,
                **definition.identity.public(),
                "indicator_family": definition.manifest.indicator_family,
                "baseline_component_indicator_id": definition.manifest.baseline_component_indicator_id,
            }
            axis = _indicator_playbook_axis(
                result,
                data=data,
                source_evidence=source_evidence,
            )
            axes.append(axis)
            evidence.append(source_evidence | {"candidate_count": len(axis.candidates)})
    return indicators, evidence, axes


def _indicator_playbook_axis(
    result: Any,
    *,
    data: MarketDataBundle,
    source_evidence: dict[str, Any],
) -> IndicatorPlaybookAxis:
    source_id = str(source_evidence["id"])
    source_key = _indicator_source_key(source_id)
    variants = result.get("variant_records") if isinstance(result, Mapping) else None
    if not isinstance(variants, list):
        raise TypeError(f"playbook {source_id!r} result variant_records must be a list")
    if not variants:
        raise ValueError(f"indicator playbook {source_id!r} must emit at least one candidate")

    close = data.feature("Close")
    candidates: list[IndicatorPlaybookCandidate] = []
    seen_candidate_ids: set[str] = set()
    for index, item in enumerate(variants):
        if not isinstance(item, Mapping):
            raise TypeError(
                f"playbook {source_id!r} result variant_records[{index}] must be a mapping"
            )
        record = dict(item)
        forbidden = sorted(set(record) & INDICATOR_CANDIDATE_FORBIDDEN_KEYS)
        if forbidden:
            raise ValueError(
                f"indicator playbook {source_id!r} result variant_records[{index}] must not "
                f"contain signal, metric, or portfolio fields: {forbidden}"
            )
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise TypeError(
                f"playbook {source_id!r} result variant_records[{index}] must include "
                "a non-empty candidate_id"
            )
        _assert_candidate_id_shape(
            candidate_id,
            source_id=source_id,
            index=index,
            field_name="candidate_id",
        )
        if candidate_id in seen_candidate_ids:
            raise ValueError(
                f"indicator playbook {source_id!r} emitted duplicate candidate {candidate_id!r}"
            )
        seen_candidate_ids.add(candidate_id)
        if not isinstance(record.get("params"), Mapping):
            raise TypeError(
                f"playbook {source_id!r} result variant_records[{index}].params must be "
                "a mapping of swept parameter names to values"
            )
        params = dict(record["params"])
        outputs = record.get("outputs")
        if not isinstance(outputs, Mapping) or not outputs:
            raise TypeError(
                f"playbook {source_id!r} result variant_records[{index}].outputs must be "
                "a non-empty mapping of output names to pandas objects"
            )
        normalized_outputs = {
            _indicator_output_name(output_name, source_id=source_id, index=index): _indicator_output_frame(
                output,
                close,
                f"indicator playbook {source_id!r} candidate {candidate_id!r} output {output_name!r}",
            )
            for output_name, output in outputs.items()
        }
        evidence = source_evidence | {
            "candidate_id": candidate_id,
            "params": to_builtin(params),
            "outputs": sorted(normalized_outputs),
            "source_key": source_key,
        }
        candidates.append(
            IndicatorPlaybookCandidate(
                source_key=source_key,
                source_id=source_id,
                candidate_id=candidate_id,
                params=params,
                outputs=normalized_outputs,
                evidence=evidence,
            )
        )

    return IndicatorPlaybookAxis(
        source_key=source_key,
        source_id=source_id,
        candidates=tuple(candidates),
    )


def _indicator_contexts(
    fixed_indicators: dict[str, Any],
    fixed_evidence: list[dict[str, Any]],
    axes: list[IndicatorPlaybookAxis],
) -> list[IndicatorContext]:
    if not axes:
        return [
            IndicatorContext(
                context_id="fixed-indicators",
                indicators=dict(fixed_indicators),
                evidence=list(fixed_evidence),
                candidate_evidence=[],
                required_indicator_keys=(),
            )
        ]

    contexts: list[IndicatorContext] = []
    for candidates in product(*(axis.candidates for axis in axes)):
        indicators = dict(fixed_indicators)
        candidate_evidence: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate.source_key in indicators:
                raise ValueError(f"duplicate strategy indicator input key: {candidate.source_key}")
            indicators[candidate.source_key] = {
                "candidate_id": candidate.candidate_id,
                "params": to_builtin(candidate.params),
                "outputs": candidate.outputs,
            }
            candidate_evidence.append(candidate.evidence)
        contexts.append(
            IndicatorContext(
                context_id=_indicator_context_id(candidate_evidence),
                indicators=indicators,
                evidence=[*fixed_evidence, *candidate_evidence],
                candidate_evidence=candidate_evidence,
                required_indicator_keys=tuple(candidate.source_key for candidate in candidates),
            )
        )
    return contexts


def _composition_diagnostics(axes: list[IndicatorPlaybookAxis]) -> dict[str, Any]:
    return {
        "schema_version": "strategy_composition.v1",
        "planned": {
            "indicator_axes": [
                {
                    "source_key": axis.source_key,
                    "source_id": axis.source_id,
                    "candidate_count": len(axis.candidates),
                }
                for axis in axes
            ],
            "indicator_context_count": _indicator_context_count(axes),
        },
        "strategy_contexts": {},
        "total_composed_candidates": 0,
    }


def _indicator_context_count(axes: list[IndicatorPlaybookAxis]) -> int:
    count = 1
    for axis in axes:
        count *= len(axis.candidates)
    return count


def _indicator_source_key(source_id: str) -> str:
    return f"playbook:{source_id}"


def _indicator_context_id(candidate_evidence: list[dict[str, Any]]) -> str:
    tokens = [
        f"{item['source']}:{item['id']}:{item['candidate_id']}" for item in candidate_evidence
    ]
    return "indicators:[" + ",".join(tokens) + "]"


def _indicator_output_name(output_name: Any, *, source_id: str, index: int) -> str:
    if not isinstance(output_name, str) or not output_name:
        raise TypeError(
            f"playbook {source_id!r} result variant_records[{index}].outputs keys must be "
            "non-empty strings"
        )
    return output_name


def _indicator_output_frame(value: Any, close: pd.DataFrame, label: str) -> pd.DataFrame:
    frame = value.to_frame() if isinstance(value, pd.Series) else value
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas Series or DataFrame")
    _assert_indicator_frame(frame, close, label)
    return frame


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
    playbook_registry: FrozenPlaybookRegistry,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    indicator_contexts: list[IndicatorContext],
    portfolio_config: Any,
    report_config: Any,
    composition_diagnostics: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if ref.source == "playbook":
        definition = playbook_registry.get(PlaybookSelection("strategies", ref.id))
        strategy_callable = definition.load_callable()
        records: list[dict[str, Any]] = []
        signal_diagnostics = _empty_signal_diagnostics()
        portfolio_diagnostics = _empty_portfolio_diagnostics()
        for context in indicator_contexts:
            inputs = _strategy_inputs_for_context(
                data=data,
                context=context,
                metadata={
                    "strategy_id": ref.id,
                    "playbook_source_hash": definition.identity.source_hash,
                    "indicator_ids": [item["id"] for item in context.evidence],
                    "indicator_context_id": context.context_id,
                },
            )
            context_records, context_signal_diagnostics, context_portfolio_diagnostics = (
                _score_strategy_playbook_candidates(
                    strategy_callable(inputs),
                    inputs,
                    data=data,
                    open_prices=open_prices,
                    portfolio_config=portfolio_config,
                    report_config=report_config,
                    source_id=definition.id,
                    source_hash=definition.identity.source_hash,
                    context=context,
                )
            )
            _record_context_composition(
                composition_diagnostics,
                context,
                strategy_candidate_count=len(context_records),
            )
            records.extend(context_records)
            signal_diagnostics["candidates"].update(context_signal_diagnostics["candidates"])
            portfolio_diagnostics["candidates"].update(
                context_portfolio_diagnostics["candidates"]
            )
        return (
            {
                "source": "playbook",
                "id": definition.id,
                "version": definition.manifest.version,
                **definition.identity.public(),
                "consumes_runner_data": True,
                "data_binding": "strategy_inputs",
            },
            records,
            signal_diagnostics,
            portfolio_diagnostics,
        )

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


def _score_strategy_playbook_candidates(
    result: Any,
    inputs: StrategyInputs,
    *,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    portfolio_config: Any,
    report_config: Any,
    source_id: str,
    source_hash: str,
    context: IndicatorContext,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    _assert_strategy_consumed_indicator_context(inputs, strategy_id=source_id)
    reject_batched_result_in_record_runner(result, source_id=source_id)
    candidates = _strategy_playbook_candidate_records(result, source_id=source_id)
    records: list[dict[str, Any]] = []
    signal_diagnostics = _empty_signal_diagnostics()
    portfolio_diagnostics = _empty_portfolio_diagnostics()
    for candidate in candidates:
        strategy_candidate_id = str(candidate["variant_id"])
        variant_id = _composed_candidate_id(
            strategy_source="playbook",
            strategy_id=source_id,
            strategy_candidate_id=strategy_candidate_id,
            indicator_candidates=context.candidate_evidence,
        )
        record, signal_diagnostic, portfolio_diagnostic = _score_strategy_signals(
            validate_strategy_output(candidate, inputs),
            data=data,
            open_prices=open_prices,
            portfolio_config=portfolio_config,
            report_config=report_config,
            variant_id=variant_id,
            params=candidate["params"],
            source_fields={
                "composed_candidate_id": variant_id,
                "strategy_source": "playbook",
                "strategy_id": source_id,
                "strategy_candidate_id": strategy_candidate_id,
                "strategy_params": to_builtin(dict(candidate["params"])),
                "source_hash": source_hash,
                "indicators": context.evidence,
                "indicator_candidates": context.candidate_evidence,
            },
        )
        records.append(record)
        signal_diagnostics["candidates"][variant_id] = signal_diagnostic
        portfolio_diagnostics["candidates"][variant_id] = portfolio_diagnostic
    return records, signal_diagnostics, portfolio_diagnostics


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
        "schema_version": "strategy_portfolio_candidate_diagnostics.v1",
        "candidates": {},
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


def _assert_candidate_id_shape(
    value: str,
    *,
    source_id: str,
    index: int,
    field_name: str,
) -> None:
    if not COMPONENT_ID_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError(
            f"playbook {source_id!r} result variant_records[{index}].{field_name} must "
            "contain only letters, numbers, dots, underscores, and hyphens"
        )


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


def _strategy_playbook_candidate_records(
    result: Any,
    *,
    source_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(result, Mapping):
        raise TypeError(f"playbook {source_id!r} result must be a mapping")
    variants = result.get("variant_records")
    if not isinstance(variants, list):
        raise TypeError(f"playbook {source_id!r} result variant_records must be a list")
    if not variants:
        raise ValueError(f"playbook {source_id!r} must emit at least one executable candidate")
    records: list[dict[str, Any]] = []
    seen_variant_ids: set[str] = set()
    forbidden_fields = STRATEGY_OUTPUT_FORBIDDEN_KEYS | PLAYBOOK_METRIC_SOURCE_KEYS
    for index, item in enumerate(variants):
        if not isinstance(item, Mapping):
            raise TypeError(
                f"playbook {source_id!r} result variant_records[{index}] must be a mapping"
            )
        record = dict(item)
        variant_id = record.get("variant_id")
        if not isinstance(variant_id, str) or not variant_id:
            raise TypeError(
                f"playbook {source_id!r} result variant_records[{index}] must include "
                "a non-empty variant_id"
            )
        _assert_candidate_id_shape(
            variant_id,
            source_id=source_id,
            index=index,
            field_name="variant_id",
        )
        if variant_id in seen_variant_ids:
            raise ValueError(f"playbook {source_id!r} emitted duplicate candidate {variant_id!r}")
        seen_variant_ids.add(variant_id)
        if not isinstance(record.get("params"), Mapping):
            raise TypeError(
                f"playbook {source_id!r} result variant_records[{index}].params must be "
                "a mapping of swept parameter names to values"
            )
        record["params"] = dict(record["params"])
        forbidden = sorted(set(record) & forbidden_fields)
        if forbidden:
            raise ValueError(
                f"playbook {source_id!r} result variant_records[{index}] must not contain "
                f"metric or portfolio fields: {forbidden}"
            )
        if "entries" not in record or "exits" not in record:
            raise ValueError(
                f"playbook {source_id!r} result variant_records[{index}] must include entries and exits"
            )
        record["variant_id"] = variant_id
        records.append(record)
    return records


def _reject_playbook_metric_records(result: Any, *, source_id: str) -> None:
    if not isinstance(result, Mapping):
        raise TypeError(f"playbook {source_id!r} result must be a mapping")
    variants = result.get("variant_records")
    if not isinstance(variants, list):
        raise TypeError(f"playbook {source_id!r} result variant_records must be a list")
    for index, item in enumerate(variants):
        if not isinstance(item, Mapping):
            raise TypeError(
                f"playbook {source_id!r} result variant_records[{index}] must be a mapping"
            )
        forbidden = sorted(set(item) & PLAYBOOK_METRIC_SOURCE_KEYS)
        if forbidden:
            raise ValueError(
                f"playbook {source_id!r} result variant_records[{index}] must not contain "
                f"leaderboard metric fields: {forbidden}"
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
            "strategy_data_binding": "strategy_inputs",
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
    artifact_path = Path("strategy_run.json")
    recorder.artifacts.plan_artifact(
        artifact_id="strategy.run",
        role="strategy_sweep_evidence",
        artifact_type="json",
        producer_stage="strategy_run",
        path=str(artifact_path),
        schema_version=STRATEGY_ARTIFACT_SCHEMA_VERSION,
    )
    recorder.artifacts.begin_artifact_write("strategy.run")
    full_path = recorder.run_dir / artifact_path
    atomic_write_json(full_path, payload)
    recorder.artifacts.complete_artifact(
        "strategy.run",
        content_hash=hash_file(full_path),
        size=full_path.stat().st_size,
        shape={"leaderboard_rows": len(payload["leaderboard"]["rows"])},
    )


def _true_count(value: pd.DataFrame | pd.Series) -> int:
    return int(value.to_numpy(dtype=bool).sum())
