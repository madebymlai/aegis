from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.component_registry import (
    ComponentDefinition,
    ComponentFamily,
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.config import (
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    to_builtin,
)
from research.aegis_research.data import MarketDataBundle
from research.aegis_research.optimization.source import OptimizationSource

COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION = "component_optimization_source.v1"
FIXED_CANDIDATE_PARAM = "__aegis_fixed_candidate__"
PARAM_KEY_PREFIX = "component"
PARAM_KEY_SEPARATOR = "|"

ResolvedComponentParams = Mapping[tuple[ComponentFamily, str, str], Mapping[str, Any]]


class ComponentSourceError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentStrategyInputs:
    data: MarketDataBundle
    indicators: Mapping[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _ComponentRuntime:
    family: ComponentFamily
    slot: str
    ref: RunSourceRefConfig | RunIndicatorSourceConfig
    definition: ComponentDefinition
    callable: Any
    fixed_params: dict[str, Any]
    param_keys: dict[str, str]


def component_ref_key(
    family: ComponentFamily,
    component_id: str,
    slot: str,
) -> tuple[ComponentFamily, str, str]:
    return (family, component_id, slot)


def component_param_key(
    family: ComponentFamily,
    component_id: str,
    slot: str,
    param_name: str,
) -> str:
    parts = (PARAM_KEY_PREFIX, family, component_id, slot, param_name)
    for part in parts:
        if not part or PARAM_KEY_SEPARATOR in part:
            raise ComponentSourceError(
                f"component param namespace part {part!r} must not be empty or contain "
                f"{PARAM_KEY_SEPARATOR!r}"
            )
    return PARAM_KEY_SEPARATOR.join(parts)


def parse_component_param_key(key: str) -> dict[str, str]:
    parts = key.split(PARAM_KEY_SEPARATOR)
    if len(parts) != 5 or parts[0] != PARAM_KEY_PREFIX:
        raise ComponentSourceError(f"not a component param key: {key!r}")
    _, family, component_id, slot, param_name = parts
    if family not in {"indicators", "strategies"}:
        raise ComponentSourceError(f"unsupported component param family: {family!r}")
    return {
        "family": family,
        "component_id": component_id,
        "slot": slot,
        "param_name": param_name,
    }


def component_param_slices(param_row: Mapping[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    slices: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, value in param_row.items():
        if key == FIXED_CANDIDATE_PARAM:
            continue
        parsed = parse_component_param_key(key)
        slice_key = (parsed["family"], parsed["component_id"], parsed["slot"])
        slices.setdefault(slice_key, {})[parsed["param_name"]] = value
    return slices


def build_component_optimization_source(
    config: RunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    data: MarketDataBundle,
    resolved_component_params: ResolvedComponentParams | None = None,
) -> OptimizationSource:
    resolved_params = resolved_component_params or {}
    strategy = _build_runtime(
        "strategies",
        "strategy",
        config.strategy,
        component_registry=component_registry,
        resolved_component_params=resolved_params,
    )
    indicators = tuple(
        _build_runtime(
            "indicators",
            ref.id,
            ref,
            component_registry=component_registry,
            resolved_component_params=resolved_params,
        )
        for ref in config.indicators
    )
    _assert_output_contract(strategy, indicators)

    params: dict[str, vbt.Param] = {}
    for runtime in (*indicators, strategy):
        for param_name, param_key in runtime.param_keys.items():
            param = _load_param_space(runtime.definition)[param_name]
            if param_key in params:
                raise ComponentSourceError(f"duplicate component param key: {param_key}")
            params[param_key] = param
    if not params:
        params[FIXED_CANDIDATE_PARAM] = vbt.Param([0])

    input_names = _input_names(strategy, indicators)

    def pipeline(close_slice: pd.DataFrame, **raw_params: Any) -> Mapping[str, Any]:
        data_slice = _slice_data(data, close_slice, input_names)
        indicator_outputs: dict[str, pd.DataFrame] = {}
        for runtime in indicators:
            output = runtime.callable(data_slice, **_params_for_runtime(runtime, raw_params))
            for output_name, frame in _coerce_indicator_outputs(
                output,
                runtime.definition,
                close_slice,
            ).items():
                if output_name in indicator_outputs:
                    raise ComponentSourceError(f"duplicate indicator output {output_name!r}")
                indicator_outputs[output_name] = frame
        strategy_inputs = ComponentStrategyInputs(
            data=data_slice,
            indicators=indicator_outputs,
            metadata={
                "strategy_id": strategy.definition.id,
                "indicator_ids": [runtime.definition.id for runtime in indicators],
                "component_optimization_source": COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION,
            },
        )
        return strategy.callable(strategy_inputs, **_params_for_runtime(strategy, raw_params))

    evidence = _source_evidence(strategy, indicators, params)
    return OptimizationSource(
        pipeline=pipeline,
        params=params,
        evidence=evidence,
        diagnostics={
            "schema_version": COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION,
            "candidate_param_count": len(params),
            "uses_fixed_candidate_param": list(params) == [FIXED_CANDIDATE_PARAM],
        },
        metadata={
            "schema_version": COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION,
            "param_namespace": PARAM_KEY_PREFIX,
        },
    )


def _build_runtime(
    family: ComponentFamily,
    slot: str,
    ref: RunSourceRefConfig | RunIndicatorSourceConfig,
    *,
    component_registry: FrozenComponentRegistry,
    resolved_component_params: ResolvedComponentParams,
) -> _ComponentRuntime:
    definition = component_registry.get(ComponentSelection(family, ref.id))
    param_space = {} if _is_locked(ref) else _load_param_space(definition)
    fixed_params = _fixed_params_for_ref(
        family,
        slot,
        ref,
        definition,
        resolved_component_params,
        param_space=param_space,
    )
    _validate_component_param_sources(definition, fixed_params, param_space)
    param_keys = {
        param_name: component_param_key(family, definition.id, slot, param_name)
        for param_name in param_space
        if param_name not in fixed_params
    }
    return _ComponentRuntime(
        family=family,
        slot=slot,
        ref=ref,
        definition=definition,
        callable=definition.load_callable(),
        fixed_params=fixed_params,
        param_keys=param_keys,
    )


def _fixed_params_for_ref(
    family: ComponentFamily,
    slot: str,
    ref: RunSourceRefConfig | RunIndicatorSourceConfig,
    definition: ComponentDefinition,
    resolved_component_params: ResolvedComponentParams,
    *,
    param_space: Mapping[str, vbt.Param],
) -> dict[str, Any]:
    if _is_locked(ref):
        key = component_ref_key(family, definition.id, slot)
        try:
            fixed = dict(resolved_component_params[key])
        except KeyError as error:
            raise ComponentSourceError(
                f"component {family}/{definition.id} slot {slot!r} requires resolved "
                "lock_id/candidate_id params before execution"
            ) from error
    else:
        fixed = {
            name: value
            for name, value in getattr(definition.manifest, "defaults", {}).items()
            if name not in param_space
        }
        fixed.update(dict(ref.params))
    unknown = sorted(set(fixed) - set(getattr(definition.manifest, "param_names", ())))
    if unknown:
        raise ComponentSourceError(
            f"component {family}/{definition.id} fixed params are not declared: {unknown}"
        )
    return fixed


def _is_locked(ref: RunSourceRefConfig | RunIndicatorSourceConfig) -> bool:
    return ref.lock_id is not None or ref.candidate_id is not None


def _load_param_space(definition: ComponentDefinition) -> dict[str, vbt.Param]:
    callable_name = getattr(definition.manifest, "param_space_callable", None)
    if callable_name is None:
        return {}
    result = definition.load_attribute(callable_name)()
    if not isinstance(result, Mapping):
        raise ComponentSourceError(
            f"component {definition.family}/{definition.id} param space must return a mapping"
        )
    params: dict[str, vbt.Param] = {}
    for param_name, param in result.items():
        if not isinstance(param_name, str) or not param_name:
            raise ComponentSourceError(
                f"component {definition.family}/{definition.id} param names must be non-empty strings"
            )
        if not isinstance(param, vbt.Param):
            raise ComponentSourceError(
                f"component {definition.family}/{definition.id} param {param_name!r} "
                "must be a vectorbtpro vbt.Param"
            )
        params[param_name] = param
    unknown = sorted(set(params) - set(getattr(definition.manifest, "param_names", ())))
    if unknown:
        raise ComponentSourceError(
            f"component {definition.family}/{definition.id} param space returned undeclared "
            f"params: {unknown}"
        )
    return params


def _validate_component_param_sources(
    definition: ComponentDefinition,
    fixed_params: Mapping[str, Any],
    param_space: Mapping[str, vbt.Param],
) -> None:
    missing = sorted(
        set(getattr(definition.manifest, "param_names", ())) - set(fixed_params) - set(param_space)
    )
    if missing:
        raise ComponentSourceError(
            f"component {definition.family}/{definition.id} has no fixed value or param space "
            f"for params: {missing}"
        )


def _params_for_runtime(runtime: _ComponentRuntime, raw_params: Mapping[str, Any]) -> dict[str, Any]:
    params = dict(runtime.fixed_params)
    for param_name, param_key in runtime.param_keys.items():
        params[param_name] = raw_params[param_key]
    return params


def _input_names(
    strategy: _ComponentRuntime,
    indicators: tuple[_ComponentRuntime, ...],
) -> tuple[str, ...]:
    names: list[str] = []
    for runtime in (*indicators, strategy):
        for name in runtime.definition.input_names:
            if name not in names:
                names.append(name)
    if "Close" not in names:
        names.append("Close")
    return tuple(names)


def _slice_data(
    data: MarketDataBundle,
    close_slice: pd.DataFrame,
    input_names: tuple[str, ...],
) -> MarketDataBundle:
    features: dict[str, pd.DataFrame] = {}
    for name in input_names:
        features[name] = close_slice if name == "Close" else data.feature(name).loc[close_slice.index]
    return MarketDataBundle(
        features=features,
        metadata=dict(data.metadata),
        native_data=data.native_data,
        loaded_features=tuple(features),
    )


def _coerce_indicator_outputs(
    output: Any,
    definition: ComponentDefinition,
    close: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    output_names = tuple(getattr(definition.manifest, "output_names", ()))
    if isinstance(output, Mapping):
        missing = sorted(set(output_names) - set(output))
        unknown = sorted(set(output) - set(output_names))
        if missing or unknown:
            raise ComponentSourceError(
                f"indicator {definition.id!r} output mismatch; missing={missing}, unknown={unknown}"
            )
        return {
            output_name: _coerce_indicator_frame(output[output_name], close, definition.id)
            for output_name in output_names
        }
    if len(output_names) != 1:
        raise ComponentSourceError(
            f"indicator {definition.id!r} must return a mapping for outputs {list(output_names)}"
        )
    return {output_names[0]: _coerce_indicator_frame(output, close, definition.id)}


def _coerce_indicator_frame(value: Any, close: pd.DataFrame, component_id: str) -> pd.DataFrame:
    frame = value.to_frame() if isinstance(value, pd.Series) else value
    if not isinstance(frame, pd.DataFrame):
        raise ComponentSourceError(f"indicator {component_id!r} output must be a pandas object")
    if not frame.index.equals(close.index):
        raise ComponentSourceError(f"indicator {component_id!r} output has misaligned timestamps")
    if list(map(str, frame.columns)) != list(map(str, close.columns)):
        raise ComponentSourceError(f"indicator {component_id!r} output has misaligned symbols")
    return frame


def _assert_output_contract(
    strategy: _ComponentRuntime,
    indicators: tuple[_ComponentRuntime, ...],
) -> None:
    produced: dict[str, str] = {}
    for runtime in indicators:
        for output_name in getattr(runtime.definition.manifest, "output_names", ()):
            previous = produced.get(output_name)
            if previous is not None:
                raise ComponentSourceError(
                    f"indicator output {output_name!r} is produced by both {previous!r} "
                    f"and {runtime.definition.id!r}"
                )
            produced[output_name] = runtime.definition.id
    missing = sorted(set(getattr(strategy.definition.manifest, "consumes_outputs", ())) - set(produced))
    if missing:
        raise ComponentSourceError(
            f"strategy {strategy.definition.id!r} consumes outputs not produced by indicators: {missing}"
        )


def _source_evidence(
    strategy: _ComponentRuntime,
    indicators: tuple[_ComponentRuntime, ...],
    params: Mapping[str, vbt.Param],
) -> dict[str, Any]:
    return {
        "schema_version": COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION,
        "source": "component",
        "kind": "component_composition",
        "strategy": _runtime_evidence(strategy),
        "indicators": [_runtime_evidence(runtime) for runtime in indicators],
        "param_names": list(params),
        "fixed_candidate_param": FIXED_CANDIDATE_PARAM if list(params) == [FIXED_CANDIDATE_PARAM] else None,
        "produced_outputs": [
            output_name
            for runtime in indicators
            for output_name in getattr(runtime.definition.manifest, "output_names", ())
        ],
        "consumed_outputs": list(getattr(strategy.definition.manifest, "consumes_outputs", ())),
    }


def _runtime_evidence(runtime: _ComponentRuntime) -> dict[str, Any]:
    return {
        "family": runtime.family,
        "slot": runtime.slot,
        "id": runtime.definition.id,
        "version": runtime.definition.manifest.version,
        **runtime.definition.identity.public(),
        "lock_id": runtime.ref.lock_id,
        "candidate_id": runtime.ref.candidate_id,
        "fixed_params": to_builtin(runtime.fixed_params),
        "param_keys": dict(runtime.param_keys),
        "param_mode": _param_mode(runtime),
    }


def _param_mode(runtime: _ComponentRuntime) -> str:
    if _is_locked(runtime.ref):
        return "locked"
    if runtime.param_keys:
        return "parameterized"
    return "fixed"
