"""Optimization source contract.

Signal-side parameter optimization only. A source exposes a
``pipeline`` callable plus a ``params`` mapping of ``vbt.Param`` axes; VBT
sweeps that grid via ``vbt.cv_split`` and Aegis computes central portfolio
metrics from the returned (entries, exits) signals.

Limitations carried by this contract:

- Portfolio-side params (``sl_stop``, ``tp_stop``, ``fees``, ``slippage``,
  ``init_cash``, ``entry_budget``, ``direction``) cannot currently be wrapped
  in ``vbt.Param``. ``simulate_portfolio`` receives a static
  ``PortfolioConfig`` per run, so any portfolio-axis sweep would not flow
  through the Aegis-owned portfolio policy boundary.

- Hidden params (``vbt.Param(..., hide=True)``) are rejected at validation
  time. They are excluded from the VBT result index, so candidate identity
  would silently collapse across hidden values.

- Component-native optimization composes configured indicator and strategy
  components before this generic runner contract. Legacy playbook optimization
  sources are no longer a forward authoring path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from vectorbtpro import vbt

OPTIMIZATION_SOURCE_CONTRACT = "aegis.optimization_source.v1"
OPTIMIZATION_SOURCE_KIND = "optimization_source"

OPTIMIZATION_SOURCE_ALLOWED_KEYS = {
    "contract",
    "kind",
    "pipeline",
    "params",
    "diagnostics",
    "metadata",
}
OPTIMIZATION_PARAM_RESERVED_NAMES = frozenset({"split", "set", "symbol", "metric_name"})
OPTIMIZATION_SOURCE_FORBIDDEN_KEYS = {
    "baseline_metric_source",
    "baseline_metrics",
    "candidate_axis",
    "composed_candidate_id",
    "entries",
    "exits",
    "materialize_signals",
    "metric_source",
    "metrics",
    "portfolio",
    "portfolio_config",
    "variant_records",
}


class OptimizationSourceError(ValueError):
    pass


@dataclass(frozen=True)
class OptimizationSource:
    pipeline: Callable[..., Any]
    params: dict[str, vbt.Param]
    evidence: dict[str, Any]
    diagnostics: dict[str, Any]
    metadata: dict[str, Any]


def validate_optimization_source(
    result: Any,
    *,
    source_evidence: Mapping[str, Any],
) -> OptimizationSource:
    if not isinstance(result, Mapping):
        raise OptimizationSourceError("optimization source must return a mapping")

    if result.get("contract") != OPTIMIZATION_SOURCE_CONTRACT:
        raise OptimizationSourceError(
            "optimization source must use contract "
            f"{OPTIMIZATION_SOURCE_CONTRACT!r}"
        )
    forbidden = sorted(set(result) & OPTIMIZATION_SOURCE_FORBIDDEN_KEYS)
    if forbidden:
        raise OptimizationSourceError(
            "optimization source must not return authoritative metrics, "
            f"portfolio fields, or candidate-axis fields: {forbidden}"
        )
    unknown = sorted(set(result) - OPTIMIZATION_SOURCE_ALLOWED_KEYS)
    if unknown:
        raise OptimizationSourceError(f"optimization source returned unknown fields: {unknown}")
    if result.get("kind") != OPTIMIZATION_SOURCE_KIND:
        raise OptimizationSourceError(
            f"optimization source kind must be {OPTIMIZATION_SOURCE_KIND!r}"
        )

    pipeline = result.get("pipeline")
    if not callable(pipeline):
        raise OptimizationSourceError("optimization source must include callable pipeline")

    params = _source_params(result.get("params"))
    diagnostics = _optional_mapping(result.get("diagnostics", {}), "diagnostics")
    metadata = _optional_mapping(result.get("metadata", {}), "metadata")
    return OptimizationSource(
        pipeline=pipeline,
        params=params,
        evidence=dict(source_evidence),
        diagnostics=diagnostics,
        metadata=metadata,
    )


def _source_params(value: Any) -> dict[str, vbt.Param]:
    if not isinstance(value, Mapping) or not value:
        raise OptimizationSourceError("optimization source params must be a non-empty mapping")
    params: dict[str, vbt.Param] = {}
    for name, param in value.items():
        if not isinstance(name, str) or not name:
            raise OptimizationSourceError("optimization param names must be non-empty strings")
        if name in OPTIMIZATION_PARAM_RESERVED_NAMES:
            raise OptimizationSourceError(
                f"optimization param name {name!r} is reserved for Aegis/VBT result "
                "coordinates; choose a distinct parameter name"
            )
        if not isinstance(param, vbt.Param):
            raise OptimizationSourceError(
                f"optimization param {name!r} must be a vectorbtpro vbt.Param"
            )
        if getattr(param, "hide", False):
            raise OptimizationSourceError(
                f"optimization param {name!r} has hide=True, which excludes it from the "
                "VBT result index; candidate identity would then collapse different "
                "values to the same candidate_key. For now, remove hide=True or fold "
                "the hidden axis into the pipeline as a fixed constant."
            )
        params[name] = param
    return params


def _optional_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OptimizationSourceError(f"optimization source {field_name} must be a mapping")
    return dict(value)
