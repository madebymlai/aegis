from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    InstrumentId,
    LockedExecutionPlan,
)

from research.aegis_research.component_registry import (
    ComponentDefinition,
    ComponentSelection,
    FrozenComponentRegistry,
    discover_component_registry,
)
from research.aegis_research.component_registry.contracts import IndicatorManifest, StrategyManifest
from research.aegis_research.configuration import (
    LOCK_ROLES,
    RunConfig,
    load_run_config,
)
from research.aegis_research.optimization.candidate_publishing import candidate_store_path
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.lock_run import ResolvedComponentParams, resolve_lock_run
from research.aegis_research.optimization.param_namespace import ComponentRef

STRATEGY_SLOT = "strategy"
CANDIDATE_PREFIX_LENGTH = 8


class UnlockedBundleConfigError(ValueError):
    """Raised when export is attempted for a config with no single locked Candidate."""


@dataclass(frozen=True)
class BundleArtifact:
    strategy_id: str
    candidate_key: str
    version: str
    dist_name: str
    package_name: str
    wheel_filename: str
    contract: DataContract
    manifest: BundleManifest
    plan: LockedExecutionPlan
    component_sources: Mapping[str, str]


@dataclass(frozen=True)
class AssembledComponents:
    strategy: ComponentSpec
    indicators: tuple[ComponentSpec, ...]
    source_hashes: Mapping[str, str]
    source_texts: Mapping[str, str]
    lookback_bars: int = 0


def assemble_bundle(config_path: Path) -> BundleArtifact:
    component_registry = discover_component_registry()
    resolved = load_run_config(config_path, component_registry=component_registry)
    config = resolved.config
    if config.lock is None:
        raise UnlockedBundleConfigError(
            "aerd export requires a Lock. This config has no `lock:`, so its "
            "parameters resolve to no single scored Candidate - an optimization "
            "sweep defines a search over many candidates, not one. Pin a "
            "published result with `lock: run_id[:role]` and re-run export."
        )
    with CandidateStore(candidate_store_path(config)) as store:
        lock_run = resolve_lock_run(config.lock, store=store)
    instrument_ids = _instrument_ids(config)
    strategy_definition = component_registry.get(
        ComponentSelection("strategies", config.strategy.id)
    )
    strategy_manifest = _strategy_manifest(strategy_definition)
    strategy_id = strategy_definition.id
    candidate_key = lock_run.candidate_key
    candidate_prefix = _candidate_prefix(candidate_key)
    dist_name = _distribution_name(strategy_id, candidate_prefix)
    package_name = _package_name(strategy_id, candidate_prefix)
    components = _assemble_components(
        package_name=package_name,
        config=config,
        component_registry=component_registry,
        component_params=lock_run.component_params,
    )
    contract = _bundle_contract(config, components, instrument_ids)
    manifest = BundleManifest(
        run_id=lock_run.run_id,
        role=_manifest_role(config.lock.candidate_id),
        candidate_key=candidate_key,
        component_source_hashes=components.source_hashes,
        instrument_ids=instrument_ids,
    )
    plan = LockedExecutionPlan(
        strategy=components.strategy,
        indicators=components.indicators,
        gross_cap=config.portfolio.gross_cap,
        net_cap=config.portfolio.net_cap,
        direction=config.portfolio.direction,
    )
    version = strategy_manifest.version
    wheel_filename = f"{_wheel_safe(dist_name)}-{version}-py3-none-any.whl"
    return BundleArtifact(
        strategy_id=strategy_id,
        candidate_key=candidate_key,
        version=version,
        dist_name=dist_name,
        package_name=package_name,
        wheel_filename=wheel_filename,
        contract=contract,
        manifest=manifest,
        plan=plan,
        component_sources=components.source_texts,
    )


def _assemble_components(
    *,
    package_name: str,
    config: RunConfig,
    component_registry: FrozenComponentRegistry,
    component_params: ResolvedComponentParams,
) -> AssembledComponents:
    indicator_specs: list[ComponentSpec] = []
    hashes: dict[str, str] = {}
    sources: dict[str, str] = {}
    lookback_bars = 0

    for position, ref in enumerate(config.indicators):
        module_name = f"indicator_{position}"
        filename = f"{module_name}.py"
        definition = component_registry.get(ComponentSelection("indicators", ref.id))
        if not definition.has_lookback:
            raise ValueError(
                f"indicator {definition.id!r} lacks lookback() entrypoint; "
                f"every bundled component must declare its warmup bars"
            )
        indicator_manifest = _indicator_manifest(definition)
        component_ref = ComponentRef("indicators", definition.id, ref.id)
        params = dict(component_params[component_ref])
        lookback_bars = max(lookback_bars, _call_lookback(definition, params))
        indicator_specs.append(
            _component_spec(
                manifest=indicator_manifest,
                module=f"{package_name}.{module_name}",
                params=params,
            )
        )
        hashes[f"indicators/{definition.id}"] = definition.identity.source_hash
        sources[filename] = definition.file_path.read_text(encoding="utf-8")

    definition = component_registry.get(ComponentSelection("strategies", config.strategy.id))
    if not definition.has_lookback:
        raise ValueError(
            f"strategy {definition.id!r} lacks lookback() entrypoint; "
            f"every bundled component must declare its warmup bars"
        )
    strategy_manifest = _strategy_manifest(definition)
    component_ref = ComponentRef("strategies", definition.id, STRATEGY_SLOT)
    params = dict(component_params[component_ref])
    lookback_bars = max(lookback_bars, _call_lookback(definition, params))
    strategy_spec = _component_spec(
        manifest=strategy_manifest,
        module=f"{package_name}.strategy",
        params=params,
    )
    hashes[f"strategies/{definition.id}"] = definition.identity.source_hash
    sources["strategy.py"] = definition.file_path.read_text(encoding="utf-8")
    return AssembledComponents(
        strategy=strategy_spec,
        indicators=tuple(indicator_specs),
        source_hashes=hashes,
        source_texts=sources,
        lookback_bars=lookback_bars,
    )


def _indicator_manifest(definition: ComponentDefinition) -> IndicatorManifest:
    manifest = definition.manifest
    if not isinstance(manifest, IndicatorManifest):
        raise TypeError(f"component {definition.id!r} is not an indicator")
    return manifest


def _strategy_manifest(definition: ComponentDefinition) -> StrategyManifest:
    manifest = definition.manifest
    if not isinstance(manifest, StrategyManifest):
        raise TypeError(f"component {definition.id!r} is not a strategy")
    return manifest


def _component_spec(
    *,
    manifest: IndicatorManifest | StrategyManifest,
    module: str,
    params: Mapping[str, Any],
) -> ComponentSpec:
    return ComponentSpec(
        family=manifest.family,
        component_id=manifest.id,
        module=module,
        input_names=tuple(manifest.input_names),
        output_names=tuple(manifest.output_names),
        params=dict(params),
    )


def _bundle_contract(
    config: RunConfig, components: AssembledComponents, instrument_ids: Sequence[InstrumentId]
) -> DataContract:
    return DataContract(
        instrument_ids=tuple(instrument_ids),
        required_arrays=tuple(_required_arrays(components)),
        base_currency=config.data.base_currency,
        timeframe=config.data.timeframe,
        lookback_bars=components.lookback_bars,
        futures=tuple(config.data.futures),
    )


def _instrument_ids(config: RunConfig) -> tuple[InstrumentId, ...]:
    return tuple(InstrumentId.from_str(value) for value in config.data.instruments)


def _call_lookback(definition: ComponentDefinition, params: Mapping[str, Any]) -> int:
    lookback_fn = definition.load_lookback()
    result = lookback_fn(**params)
    if not isinstance(result, int) or result < 0:
        raise ValueError(
            f"component {definition.id!r} lookback() must return a non-negative int; "
            f"got {result!r}"
        )
    return result


def _required_arrays(components: AssembledComponents) -> tuple[str, ...]:
    names: list[str] = []
    for spec in (*components.indicators, components.strategy):
        for name in spec.input_names:
            if name not in names:
                names.append(name)
    if "Close" not in names:
        names.append("Close")
    return tuple(names)


def _distribution_name(strategy_id: str, candidate_prefix: str) -> str:
    return f"aegis-exec-{_slug(strategy_id)}-{candidate_prefix}"


def _package_name(strategy_id: str, candidate_prefix: str) -> str:
    return f"aegis_exec_{_module_slug(strategy_id)}_{candidate_prefix}"


def _candidate_prefix(candidate_key: str) -> str:
    if len(candidate_key) < CANDIDATE_PREFIX_LENGTH:
        raise ValueError(
            f"candidate key must have at least {CANDIDATE_PREFIX_LENGTH} characters; "
            f"got {candidate_key!r}"
        )
    return candidate_key[:CANDIDATE_PREFIX_LENGTH]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _module_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()


def _wheel_safe(value: str) -> str:
    return value.replace("-", "_")


def _manifest_role(candidate_id: str) -> str:
    return candidate_id if candidate_id in LOCK_ROLES else "candidate_key"
