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
    MissingIndexPolicy,
)
from aegis_data.marking import DeclaredMarkingResolver, MarkMode
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType

from research.aegis_research.component_registry import (
    ComponentDefinition,
    ComponentSelection,
    FrozenComponentRegistry,
    discover_component_registry,
)
from research.aegis_research.configuration import (
    LOCK_ROLES,
    RunConfig,
    load_run_config,
)
from research.aegis_research.drift_bands import instrument_bands_from
from research.aegis_research.market_data.identity import resolved_instruments
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.candidate_store_identity import candidate_store_path
from research.aegis_research.optimization.lock_run import ResolvedComponentParams, resolve_lock_run
from research.aegis_research.optimization.param_namespace import ComponentRef

STRATEGY_SLOT = "strategy"
CANDIDATE_PREFIX_LENGTH = 8


class UnlockedBundleConfigError(ValueError):
    """Raised when export is attempted for a config with no single locked Candidate."""


class UnrecordedAdjustmentModeError(ValueError):
    """Raised when a futures-declaring export's locked Run recorded no adjustment mode."""


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
    instruments = resolved_instruments(config)
    instrument_ids = tuple(instrument_id for instrument_id, _ in instruments)
    strategy_definition = component_registry.get(
        ComponentSelection("strategies", config.strategy.id)
    )
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
    contract = _bundle_contract(
        config, components, instrument_ids, adjustment_mode=lock_run.adjustment_mode
    )
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
        instrument_bands=instrument_bands_from(instruments, config.portfolio),
        gross_cap=config.portfolio.gross_cap,
        net_cap=config.portfolio.net_cap,
        direction=config.portfolio.direction,
    )
    version = strategy_definition.version
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


# Payloads ship VERBATIM (the wheel is provenance, not a transform target), so a component
# that imports a research-only dependency at module level would break the deployable at
# import time - aegis-trader excludes vectorbtpro by design, and the failure mode is the
# worst kind: "Sleeve compute FAILED ... Sleeve holds this period" on every bar, silently.
# The convention is a LAZY import inside ``param_space`` (the trader never calls it); this
# guard makes a regression loud at export instead of silent at trading time.
_TOP_LEVEL_RESEARCH_IMPORT = re.compile(
    r"^(?:from vectorbtpro\b[^\n]*|import vectorbtpro\b[^\n]*)$",
    re.MULTILINE,
)


def _assert_payload_imports_clean(filename: str, source: str) -> str:
    """Fail loud if a payload module would import research-only deps at module level."""
    match = _TOP_LEVEL_RESEARCH_IMPORT.search(source)
    if match:
        raise ValueError(
            f"execution payload {filename!r} imports a research-only dependency at module "
            f"level ({match.group(0)!r}); deployables exclude vectorbtpro, so the bundle "
            f"could not even be imported there. Move the import inside param_space() "
            f"(the research-only surface) and re-export."
        )
    return source


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
        component_ref = ComponentRef("indicators", definition.id, ref.id)
        params = dict(component_params[component_ref])
        lookback_bars = max(lookback_bars, definition.warmup_bars(params))
        indicator_specs.append(
            _component_spec(
                definition=definition,
                module=f"{package_name}.{module_name}",
                params=params,
            )
        )
        hashes[f"indicators/{definition.id}"] = definition.identity.source_hash
        sources[filename] = _assert_payload_imports_clean(filename, definition.source_text())

    definition = component_registry.get(ComponentSelection("strategies", config.strategy.id))
    if not definition.has_lookback:
        raise ValueError(
            f"strategy {definition.id!r} lacks lookback() entrypoint; "
            f"every bundled component must declare its warmup bars"
        )
    component_ref = ComponentRef("strategies", definition.id, STRATEGY_SLOT)
    params = dict(component_params[component_ref])
    lookback_bars = max(lookback_bars, definition.warmup_bars(params))
    strategy_spec = _component_spec(
        definition=definition,
        module=f"{package_name}.strategy",
        params=params,
    )
    hashes[f"strategies/{definition.id}"] = definition.identity.source_hash
    sources["strategy.py"] = _assert_payload_imports_clean(
        "strategy.py", definition.source_text()
    )
    return AssembledComponents(
        strategy=strategy_spec,
        indicators=tuple(indicator_specs),
        source_hashes=hashes,
        source_texts=sources,
        lookback_bars=lookback_bars,
    )


def _component_spec(
    *,
    definition: ComponentDefinition,
    module: str,
    params: Mapping[str, Any],
) -> ComponentSpec:
    return ComponentSpec(
        family=definition.family,
        component_id=definition.id,
        module=module,
        input_names=definition.input_names,
        output_names=definition.produced_output_names(),
        params=dict(params),
    )


def _bundle_contract(
    config: RunConfig,
    components: AssembledComponents,
    instrument_ids: Sequence[InstrumentId],
    *,
    adjustment_mode: ContinuousFutureAdjustmentType | None,
) -> DataContract:
    futures = tuple(config.data.futures)
    if futures and adjustment_mode is None:
        # Never fall back to the current DEFAULT_ADJUSTMENT_MODE: the export must
        # declare the algebra the locked Run's frames were actually built under.
        raise UnrecordedAdjustmentModeError(
            f"this export declares continuous-future roots {sorted(futures)}, but the "
            "locked Run recorded no adjustment mode (it predates adjustment-mode "
            "evidence). Historical futures frames cannot prove which re-basing "
            "algebra they used - re-run the optimization under the current research "
            "code, then re-lock and re-export."
        )
    exchange = tuple(InstrumentId.from_str(value) for value in config.data.exchange)
    return DataContract(
        instrument_ids=tuple(instrument_ids),
        required_arrays=tuple(_required_arrays(components)),
        base_currency=config.data.base_currency,
        timeframe=config.data.timeframe,
        missing_index=MissingIndexPolicy(config.data.missing_index),
        lookback_bars=components.lookback_bars,
        futures=futures,
        exchange=exchange,
        adjustment_mode=adjustment_mode if futures else None,
        mark_modes=_recorded_mark_modes(config, instrument_ids, futures, exchange),
    )


def _recorded_mark_modes(
    config: RunConfig,
    instrument_ids: Sequence[InstrumentId],
    futures: tuple[str, ...],
    exchange: tuple[InstrumentId, ...],
) -> dict[InstrumentId, str]:
    """The resolved mark mode per loadable leg, pinned into the export.

    The same resolution research loaded under (the declared token + the corpus
    defaults), recorded explicitly for every static leg — LAST included — so
    live consumes the mark and never re-derives it (aegis-rd-tggo.3).
    Continuous roots are LAST by construction and are not recorded.
    """
    resolver = DeclaredMarkingResolver(
        declared={
            InstrumentId.from_str(value): MarkMode(mode)
            for value, mode in config.data.mark_modes.items()
        }
    )
    continuous_symbols = set(futures)
    loadable = (
        *(
            instrument_id
            for instrument_id in instrument_ids
            if instrument_id.symbol.value not in continuous_symbols
        ),
        *exchange,
    )
    return {
        instrument_id: resolver.resolve(instrument_id, config.data.timeframe).mode.value
        for instrument_id in loadable
    }


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
