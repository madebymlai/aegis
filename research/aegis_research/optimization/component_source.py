from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.component_registry import (
    ComponentDefinition,
    ComponentFamily,
    ComponentSelection,
    FrozenComponentRegistry,
    IndicatorManifest,
    StrategyManifest,
)
from research.aegis_research.configuration import (
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    to_builtin,
)
from research.aegis_research.data import MarketDataBundle
from research.aegis_research.optimization.param_namespace import (
    FIXED_CANDIDATE_PARAM,
    PARAM_KEY_PREFIX,
    ComponentRef,
    encode,
)
from research.aegis_research.optimization.precompute import (
    CandidateKey,
    IndicatorPrecompute,
    build_candidate_index,
    candidate_keys,
)
from research.aegis_research.optimization.source import OptimizationSource

COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION = "component_optimization_source.v2"

ResolvedComponentParams = Mapping[ComponentRef, Mapping[str, Any]]


class ComponentSourceError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentStrategyInputs:
    data: MarketDataBundle
    indicators: Mapping[str, np.ndarray]
    n_candidates: int
    n_symbols: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _ComponentRuntime:
    family: ComponentFamily
    slot: str
    ref: RunSourceRefConfig | RunIndicatorSourceConfig
    definition: ComponentDefinition
    callable: Any
    fixed_params: dict[str, Any]
    param_space: dict[str, vbt.Param]
    param_keys: dict[str, str]
    locked: bool


@dataclass(frozen=True)
class _RuntimeParamDeduplication:
    param_lists: dict[str, list[Any]]
    candidate_index: dict[CandidateKey, int]
    n_candidates: int


def build_component_optimization_source(
    config: RunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    data: MarketDataBundle,
    resolved_component_params: ResolvedComponentParams | None = None,
    force_locked: bool = False,
) -> OptimizationSource:
    resolved_params = resolved_component_params or {}
    strategy = _build_runtime(
        "strategies",
        "strategy",
        config.strategy,
        component_registry=component_registry,
        resolved_component_params=resolved_params,
        force_locked=force_locked,
    )
    indicators = tuple(
        _build_runtime(
            "indicators",
            ref.id,
            ref,
            component_registry=component_registry,
            resolved_component_params=resolved_params,
            force_locked=force_locked,
        )
        for ref in config.indicators
    )
    _assert_output_contract(strategy, indicators)

    params: dict[str, vbt.Param] = {}
    for runtime in (*indicators, strategy):
        for param_name, param_key in runtime.param_keys.items():
            param = runtime.param_space[param_name]
            if param_key in params:
                raise ComponentSourceError(f"duplicate component param key: {param_key}")
            params[param_key] = param
    if not params:
        params[FIXED_CANDIDATE_PARAM] = vbt.Param([0])

    input_names = _input_names(strategy, indicators)

    def precompute(
        close: pd.DataFrame, n_candidates: int, **param_lists: Any
    ) -> IndicatorPrecompute:
        # Run each indicator's batched callable once over ``close`` (the full series in
        # the selection phase) and return a candidate-major store sliceable by split
        # range. Candidates whose warmup still exceeds the full series are marked
        # invalid by the runner before ranking.
        data_full = _slice_data(data, close, input_names)
        n_symbols = len(close.columns)
        outputs: dict[str, np.ndarray] = {}
        full_candidate_keys = candidate_keys(param_lists)
        candidate_index_by_output: dict[str, dict[CandidateKey, int]] = {}
        for runtime in indicators:
            deduped = _deduplicate_runtime_params(
                runtime,
                param_lists,
                full_candidate_keys=full_candidate_keys,
                n_candidates=n_candidates,
            )
            output = runtime.callable(
                data_full, n_candidates=deduped.n_candidates, **deduped.param_lists
            )
            output_arrays = _validated_indicator_output_arrays(
                runtime,
                output,
                expected_shape=_candidate_major_shape(close, deduped.n_candidates),
            )
            for output_name, output_arr in output_arrays.items():
                if output_name in outputs:
                    raise ComponentSourceError(f"duplicate indicator output {output_name!r}")
                outputs[output_name] = output_arr
                candidate_index_by_output[output_name] = deduped.candidate_index
        return IndicatorPrecompute(
            outputs=outputs,
            candidate_index=build_candidate_index(param_lists),
            n_symbols=n_symbols,
            output_candidate_index=candidate_index_by_output,
        )

    def simulate(
        close_window: pd.DataFrame,
        indicator_window: Mapping[str, np.ndarray],
        n_candidates: int,
        **param_lists: Any,
    ) -> pd.DataFrame:
        # Run the strategy allocation for one window given indicator outputs already
        # sliced to that window; the central-metrics step prices the allocations.
        data_slice = _slice_data(data, close_window, input_names)
        n_symbols = len(close_window.columns)
        strategy_inputs = ComponentStrategyInputs(
            data=data_slice,
            indicators=indicator_window,
            n_candidates=n_candidates,
            n_symbols=n_symbols,
            metadata={
                "strategy_id": strategy.definition.id,
                "indicator_ids": [runtime.definition.id for runtime in indicators],
                "component_optimization_source": COMPONENT_OPTIMIZATION_SOURCE_SCHEMA_VERSION,
            },
        )
        strategy_params = _params_for_runtime(
            strategy, param_lists, n_candidates=n_candidates
        )
        alloc_arr = _validated_component_array(
            strategy,
            strategy.callable(
                strategy_inputs, n_candidates=n_candidates, **strategy_params
            ),
            expected_shape=_candidate_major_shape(close_window, n_candidates),
            output_label="allocation",
        )
        return _build_frame(alloc_arr, close_window, n_candidates, param_lists, params)

    evidence = _source_evidence(strategy, indicators, params)
    strategy_manifest = strategy.definition.manifest
    assert isinstance(strategy_manifest, StrategyManifest)
    return OptimizationSource(
        precompute=precompute,
        simulate=simulate,
        params=params,
        output_name=strategy_manifest.output_name,
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
    force_locked: bool = False,
) -> _ComponentRuntime:
    definition = component_registry.get(ComponentSelection(family, ref.id))
    locked = force_locked
    param_space_entrypoint_name = None if locked else definition.param_space_entrypoint_name
    attribute_names = [definition.callable_name]
    if param_space_entrypoint_name is not None:
        attribute_names.append(param_space_entrypoint_name)
    attributes = definition.load_attributes(attribute_names)
    param_space = (
        {}
        if param_space_entrypoint_name is None
        else _load_param_space(definition, attributes[param_space_entrypoint_name])
    )
    fixed_params = _fixed_params_for_ref(
        family,
        slot,
        ref,
        definition,
        resolved_component_params,
        param_space=param_space,
        force_locked=force_locked,
    )
    _validate_component_param_sources(definition, fixed_params, param_space)
    param_keys = {
        param_name: encode(ComponentRef(family, definition.id, slot), param_name)
        for param_name in param_space
        if param_name not in fixed_params
    }
    return _ComponentRuntime(
        family=family,
        slot=slot,
        ref=ref,
        definition=definition,
        callable=attributes[definition.callable_name],
        fixed_params=fixed_params,
        param_space=dict(param_space),
        param_keys=param_keys,
        locked=locked,
    )


def _fixed_params_for_ref(
    family: ComponentFamily,
    slot: str,
    ref: RunSourceRefConfig | RunIndicatorSourceConfig,
    definition: ComponentDefinition,
    resolved_component_params: ResolvedComponentParams,
    *,
    param_space: Mapping[str, vbt.Param],
    force_locked: bool = False,
) -> dict[str, Any]:
    if force_locked:
        key = ComponentRef(family, definition.id, slot)
        try:
            fixed = dict(resolved_component_params[key])
        except KeyError as error:
            raise ComponentSourceError(
                f"component {family}/{definition.id} slot {slot!r} requires resolved "
                "lock params before execution"
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


def _load_param_space(
    definition: ComponentDefinition,
    param_space_entrypoint: Any,
) -> dict[str, vbt.Param]:
    result = param_space_entrypoint()
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
        if bool(param.resolve_field("hide")):
            raise ComponentSourceError(
                f"component {definition.family}/{definition.id} param {param_name!r} has hide=True, "
                "which excludes it from the VBT result index; candidate identity would then "
                "collapse different values to the same candidate_key. Remove hide=True until "
                "hidden component params are represented in candidate identity."
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


def _params_for_runtime(
    runtime: _ComponentRuntime,
    param_lists: Mapping[str, Sequence[Any]],
    *,
    n_candidates: int,
) -> dict[str, Sequence[Any]]:
    params: dict[str, Sequence[Any]] = {}
    for param_name, param_key in runtime.param_keys.items():
        params[param_name] = param_lists[param_key]
    for param_name, fixed_value in runtime.fixed_params.items():
        params[param_name] = [fixed_value] * n_candidates
    return params


def _deduplicate_runtime_params(
    runtime: _ComponentRuntime,
    param_lists: Mapping[str, Sequence[Any]],
    *,
    full_candidate_keys: Sequence[CandidateKey],
    n_candidates: int,
) -> _RuntimeParamDeduplication:
    runtime_param_lists = _params_for_runtime(runtime, param_lists, n_candidates=n_candidates)
    runtime_param_names = sorted(runtime_param_lists)
    unique_positions: dict[tuple[Any, ...], int] = {}
    unique_param_lists: dict[str, list[Any]] = {name: [] for name in runtime_param_names}
    candidate_index: dict[CandidateKey, int] = {}

    for candidate_idx, full_key in enumerate(full_candidate_keys):
        runtime_key = tuple(
            runtime_param_lists[name][candidate_idx] for name in runtime_param_names
        )
        if runtime_key not in unique_positions:
            unique_positions[runtime_key] = len(unique_positions)
            for name in runtime_param_names:
                unique_param_lists[name].append(runtime_param_lists[name][candidate_idx])
        candidate_index[full_key] = unique_positions[runtime_key]

    return _RuntimeParamDeduplication(
        param_lists=unique_param_lists,
        candidate_index=candidate_index,
        n_candidates=len(unique_positions),
    )


def _candidate_major_shape(close: pd.DataFrame, n_candidates: int) -> tuple[int, int]:
    return (len(close), n_candidates * len(close.columns))


def _validated_indicator_output_arrays(
    runtime: _ComponentRuntime,
    output: Any,
    *,
    expected_shape: tuple[int, int],
) -> dict[str, np.ndarray]:
    manifest = runtime.definition.manifest
    assert isinstance(manifest, IndicatorManifest)
    output_names = tuple(manifest.output_names)
    if not isinstance(output, Mapping):
        raise ComponentSourceError(
            f"indicator {runtime.definition.id!r} must return a mapping for outputs "
            f"{list(output_names)}"
        )
    missing = _sorted_names(set(output_names) - set(output))
    unknown = _sorted_names(set(output) - set(output_names))
    if missing or unknown:
        raise ComponentSourceError(
            f"indicator {runtime.definition.id!r} output mismatch; "
            f"missing={missing}, unknown={unknown}"
        )
    return {
        output_name: _validated_component_array(
            runtime,
            output[output_name],
            expected_shape=expected_shape,
            output_label=f"output {output_name!r}",
        )
        for output_name in output_names
    }


def _sorted_names(names: set[Any]) -> list[Any]:
    return sorted(names, key=repr)


def _validated_component_array(
    runtime: _ComponentRuntime,
    value: Any,
    *,
    expected_shape: tuple[int, int],
    output_label: str,
) -> np.ndarray:
    arr = np.asarray(value)
    if arr.shape != expected_shape:
        raise ComponentSourceError(
            f"component {runtime.family}/{runtime.definition.id} {output_label} has "
            f"expected shape {expected_shape}; actual shape {arr.shape}"
        )
    return arr


def _build_frame(
    alloc_arr: np.ndarray,
    close_slice: pd.DataFrame,
    n_candidates: int,
    param_lists: Mapping[str, Any],
    param_defs: Mapping[str, Any],
) -> pd.DataFrame:
    symbols = close_slice.columns
    param_keys = [k for k in param_defs if k != FIXED_CANDIDATE_PARAM]
    if not param_keys:
        param_keys = [FIXED_CANDIDATE_PARAM]
    col_tuples = []
    for i in range(n_candidates):
        for sym in symbols:
            col_tuples.append((*(param_lists[k][i] for k in param_keys), sym))
    col_names = [*param_keys, "symbol"]
    col_mi = pd.MultiIndex.from_tuples(col_tuples, names=col_names)
    return pd.DataFrame(alloc_arr, index=close_slice.index, columns=col_mi)


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
    arrays: dict[str, pd.DataFrame] = {}
    for name in input_names:
        arrays[name] = (
            close_slice if name == "Close" else data.array(name).loc[close_slice.index]
        )
    return MarketDataBundle(arrays=arrays)


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
    missing = sorted(
        set(getattr(strategy.definition.manifest, "consumes_outputs", ())) - set(produced)
    )
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
        "fixed_candidate_param": FIXED_CANDIDATE_PARAM
        if list(params) == [FIXED_CANDIDATE_PARAM]
        else None,
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
        "fixed_params": to_builtin(runtime.fixed_params),
        "param_keys": dict(runtime.param_keys),
        "param_mode": _param_mode(runtime),
    }


def _param_mode(runtime: _ComponentRuntime) -> str:
    if runtime.locked:
        return "locked"
    if runtime.param_keys:
        return "parameterized"
    return "fixed"
