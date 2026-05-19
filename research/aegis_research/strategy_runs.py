from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

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
from research.aegis_research.playbook_registry.registry import execute_notebook_playbook
from research.aegis_research.portfolios import simulate_portfolio
from research.aegis_research.provenance.manifest import atomic_write_json, hash_file
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.provenance.run_store import RunStore
from research.aegis_research.reports import portfolio_metrics
from research.aegis_research.run_leaderboard import build_run_leaderboard

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


@dataclass(frozen=True)
class StrategyInputBundle:
    data: MarketDataBundle
    indicators: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class StrategySignalResult:
    entries: pd.DataFrame
    exits: pd.DataFrame
    diagnostics: dict[str, Any]


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
    array_contract = _strategy_data_array_contract(config, component_registry)
    playbooks = playbook_registry or discover_playbook_registry(component_registry=component_registry)

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
        data_result.assert_usable()
        data_bundle = market_data_bundle(data_result)
        open_prices = data_bundle.feature("Open")
        indicators, indicator_evidence, playbook_variant_records = _resolve_indicator_refs(
            config.indicators,
            component_registry=component_registry,
            playbook_registry=playbooks,
            data=data_bundle,
        )

        strategy_evidence, strategy_variant_records, signal_diagnostics, portfolio_diagnostics = (
            _resolve_strategy_ref(
                config.strategy,
                component_registry=component_registry,
                playbook_registry=playbooks,
                data=data_bundle,
                open_prices=open_prices,
                indicators=indicators,
                indicator_evidence=indicator_evidence,
                portfolio_config=config.portfolio,
                report_config=config.report,
            )
        )
        leaderboard = build_run_leaderboard(
            [*strategy_variant_records, *playbook_variant_records],
            metric=config.ranking.metric,
            direction=config.ranking.direction,
            rank_by=config.ranking.rank_by,
        )
        payload = {
            "schema_version": STRATEGY_ARTIFACT_SCHEMA_VERSION,
            "lane": "run",
            "evidence_type": "strategy_sweep",
            "strategy": strategy_evidence,
            "indicators": indicator_evidence,
            "data": data_array_evidence_payload(data_result, array_contract),
            "leaderboard": leaderboard,
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
        recorder.mark_run_interrupted(diagnostic={"error_type": "KeyboardInterrupt", "message": "interrupted"})
        raise
    except ConfigValidationError as error:
        recorder.mark_run_failed(diagnostic={"error_type": type(error).__name__, "message": str(error)[:1000]})
        raise
    except Exception as error:
        recorder.mark_run_failed(diagnostic={"error_type": type(error).__name__, "message": str(error)[:1000]})
        raise


def _resolve_indicator_refs(
    refs: list[RunIndicatorSourceConfig],
    *,
    component_registry: FrozenComponentRegistry,
    playbook_registry: FrozenPlaybookRegistry,
    data: MarketDataBundle,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    indicators: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []
    variant_records: list[dict[str, Any]] = []
    seen_playbook_ids: set[str] = set()
    for ref in refs:
        if ref.source == "component":
            component_ids = ref.expanded_ids(component_registry.ids("indicators"))
            for component_id in component_ids:
                if component_id in indicators:
                    raise ValueError(f"duplicate indicator component ref: {component_id}")
                definition = component_registry.get(ComponentSelection("indicators", component_id))
                output = definition.load_callable()(data)
                indicators[component_id] = _validate_indicator_output(output, data.close, component_id)
                evidence.append(
                    {
                        "source": "component",
                        "id": component_id,
                        "version": definition.manifest.version,
                        "source_hash": definition.identity.source_hash,
                    }
                )
            continue

        playbook_ids = ref.expanded_ids(playbook_registry.ids("indicators"))
        for playbook_id in playbook_ids:
            if playbook_id in seen_playbook_ids:
                raise ValueError(f"duplicate indicator playbook ref: {playbook_id}")
            seen_playbook_ids.add(playbook_id)
            definition = playbook_registry.get(PlaybookSelection("indicators", playbook_id))
            result = execute_notebook_playbook(definition)
            evidence.append(
                {
                    "source": "playbook",
                    "id": definition.id,
                    "version": definition.manifest.version,
                    "source_hash": definition.identity.source_hash,
                    "indicator_family": definition.manifest.indicator_family,
                    "baseline_component_indicator_id": definition.manifest.baseline_component_indicator_id,
                }
            )
            variant_records.extend(
                _playbook_variant_records(
                    result,
                    source_field="indicator_source",
                    id_field="indicator_id",
                    source="playbook",
                    source_id=definition.id,
                    source_hash=definition.identity.source_hash,
                    baseline_component_indicator_id=definition.manifest.baseline_component_indicator_id,
                )
            )
    return indicators, evidence, variant_records


def _strategy_data_array_contract(
    config: Any,
    component_registry: FrozenComponentRegistry,
) -> DataArrayContract:
    return build_data_array_contract(
        configured_arrays=config.data.effective_arrays,
        component_required_arrays=_strategy_component_required_arrays(config, component_registry),
        pipeline_required_arrays=("Close", "Open"),
    )


def _strategy_component_required_arrays(
    config: Any,
    component_registry: FrozenComponentRegistry,
) -> tuple[str, ...]:
    required: list[tuple[str, ...]] = []
    if config.strategy.source == "component":
        required.append(
            component_registry.get(ComponentSelection("strategies", config.strategy.id)).input_names
        )
    for ref in config.indicators:
        if ref.source != "component":
            continue
        for component_id in ref.expanded_ids(component_registry.ids("indicators")):
            required.append(
                component_registry.get(ComponentSelection("indicators", component_id)).input_names
            )
    return merge_data_arrays(*required)


def _resolve_strategy_ref(
    ref: RunSourceRefConfig,
    *,
    component_registry: FrozenComponentRegistry,
    playbook_registry: FrozenPlaybookRegistry,
    data: MarketDataBundle,
    open_prices: pd.DataFrame,
    indicators: dict[str, Any],
    indicator_evidence: list[dict[str, Any]],
    portfolio_config: Any,
    report_config: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if ref.source == "playbook":
        definition = playbook_registry.get(PlaybookSelection("strategies", ref.id))
        result = execute_notebook_playbook(definition)
        return (
            {
                "source": "playbook",
                "id": definition.id,
                "version": definition.manifest.version,
                "source_hash": definition.identity.source_hash,
            },
            _playbook_variant_records(
                result,
                source_field="strategy_source",
                id_field="strategy_id",
                source="playbook",
                source_id=definition.id,
                source_hash=definition.identity.source_hash,
            ),
            {},
            {},
        )

    definition = component_registry.get(ComponentSelection("strategies", ref.id))
    strategy_callable = definition.load_callable()
    bundle = StrategyInputBundle(
        data=data,
        indicators=indicators,
        metadata={
            "strategy_id": ref.id,
            "component_source_hash": definition.identity.source_hash,
            "indicator_ids": [item["id"] for item in indicator_evidence],
        },
    )
    signal_result = validate_strategy_output(strategy_callable(bundle), bundle)
    signal_config = SignalConfig()
    portfolio = simulate_portfolio(
        data.close,
        signal_result.entries,
        signal_result.exits,
        portfolio_config,
        signal_config,
        open_prices=open_prices,
        market_index=data.close.index,
    )
    metrics = portfolio_metrics(portfolio.portfolio, report_config)
    return (
        {
            "source": "component",
            "id": ref.id,
            "version": definition.manifest.version,
            "source_hash": definition.identity.source_hash,
        },
        [
            {
                "variant_id": ref.id,
                "strategy_source": "component",
                "strategy_id": ref.id,
                "component_source_hash": definition.identity.source_hash,
                "indicators": indicator_evidence,
                "metrics": metrics,
                "portfolio": to_builtin(asdict(portfolio_config)),
            }
        ],
        signal_result.diagnostics,
        portfolio.diagnostics,
    )


def _playbook_variant_records(
    result: dict[str, Any],
    *,
    source_field: str,
    id_field: str,
    source: str,
    source_id: str,
    source_hash: str,
    baseline_component_indicator_id: str | None = None,
) -> list[dict[str, Any]]:
    variants = result.get("variant_records")
    if not isinstance(variants, list):
        raise TypeError(f"playbook {source_id!r} result variant_records must be a list")
    records: list[dict[str, Any]] = []
    for index, item in enumerate(variants):
        if not isinstance(item, dict):
            raise TypeError(
                f"playbook {source_id!r} result variant_records[{index}] must be a mapping"
            )
        record = dict(item)
        record.setdefault(source_field, source)
        record.setdefault(id_field, source_id)
        record.setdefault("source_hash", source_hash)
        if baseline_component_indicator_id is not None:
            record.setdefault("baseline_component_indicator_id", baseline_component_indicator_id)
        records.append(record)
    return records


def _validate_indicator_output(output: Any, close: pd.DataFrame, component_id: str) -> Any:
    frame = output.to_frame() if isinstance(output, pd.Series) else output
    if isinstance(frame, pd.DataFrame):
        _assert_indicator_frame(frame, close, component_id)
        return frame
    result_frame = getattr(output, "frame", None)
    if isinstance(result_frame, pd.DataFrame):
        _assert_indicator_frame(result_frame, close, component_id)
        return output
    raise TypeError(f"indicator component {component_id!r} must return a pandas object or IndicatorResult")


def _assert_indicator_frame(frame: pd.DataFrame, close: pd.DataFrame, component_id: str) -> None:
    if not frame.index.equals(close.index):
        raise ValueError(f"indicator component {component_id!r} has misaligned timestamps")


def _run_refs(recorder) -> dict[str, Any]:
    return {
        "run_id": recorder.manifest.run_id,
        "run_dir": str(recorder.run_dir),
        "manifest_path": str(recorder.manifest_path),
        "status": recorder.manifest.status,
        "started_at": recorder.manifest.started_at,
        "finished_at": recorder.manifest.finished_at,
    }


def validate_strategy_output(output: Any, bundle: StrategyInputBundle) -> StrategySignalResult:
    if not isinstance(output, dict):
        raise TypeError("strategy output must be a mapping")
    forbidden = sorted(set(output) & STRATEGY_OUTPUT_FORBIDDEN_KEYS)
    if forbidden:
        raise ValueError(f"strategy output must not contain portfolio fields: {forbidden}")
    if "entries" not in output or "exits" not in output:
        raise ValueError("strategy output must include entries and exits")
    entries = _signal_frame(output["entries"], bundle.data.close, "entries")
    exits = _signal_frame(output["exits"], bundle.data.close, "exits")
    diagnostics = {
        "schema_version": "strategy_signal_diagnostics.v1",
        "entry_states": _true_count(entries),
        "exit_states": _true_count(exits),
        "symbols": [str(column) for column in entries.columns],
        "timing": "signals_are_bar_aligned_inputs_to_config_owned_portfolio_execution",
    }
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
