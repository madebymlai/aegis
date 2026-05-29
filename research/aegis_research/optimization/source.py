"""Optimization source contract.

Signal-side parameter optimization only. A source exposes two stages plus a
``params`` mapping of ``vbt.Param`` axes:

- ``precompute(close, n_candidates, **param_lists) -> WideIndicatorPrecompute``
  runs each indicator's wide callable once over the given series, returning a
  candidate-major store sliceable by split range. Run over the **full** series,
  it preserves all available warmup history; candidates whose lookback still
  exceeds that history are invalidated before ranking. Outputs must satisfy the
  ``validate_precompute_no_lookahead`` prefix-equivalence contract: truncating the
  input immediately after a row must not change that row's output values.
- ``simulate(close_window, indicator_window, n_candidates, **param_lists)``
  runs the strategy allocation for one window given the precomputed indicator
  outputs already sliced to that window (the central-metrics step then computes
  portfolio metrics from the returned allocations).

The fused per-slice view both stages compose into is available via the
``pipeline`` method (precompute-on-slice then simulate-on-slice); the runner's
selection sweep instead precomputes once over the full series and slices per
window so no candidate loses warmup to a short slice. The held-out sweep uses the
same full-series store for the representative candidates.

Limitations carried by this contract:

- Portfolio-side params (``sl_stop``, ``tp_stop``, ``fees``, ``slippage``,
  ``init_cash``, ``target_exposure_cap``, ``direction``) cannot currently be wrapped
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

from research.aegis_research.optimization.precompute import (
    WideIndicatorPrecompute,
    candidate_keys,
)
from research.aegis_research.portfolio_policy.policy import STRATEGY_ALLOCATION_OUTPUTS

OPTIMIZATION_SOURCE_CONTRACT = "aegis.optimization_source.v1"
OPTIMIZATION_SOURCE_KIND = "optimization_source"

OPTIMIZATION_SOURCE_ALLOWED_KEYS = {
    "contract",
    "kind",
    "precompute",
    "simulate",
    "params",
    "output_name",
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
    precompute: Callable[..., WideIndicatorPrecompute]
    simulate: Callable[..., Any]
    params: dict[str, vbt.Param]
    output_name: str
    evidence: dict[str, Any]
    diagnostics: dict[str, Any]
    metadata: dict[str, Any]

    def pipeline(self, close: Any, n_candidates: int, **param_lists: Any) -> Any:
        """Fused per-slice view: precompute on ``close`` then simulate that window.

        Used where callers explicitly need indicators computed on the same window
        they are simulated on (for example, fused-pipeline tests). The runner does
        not use this for split sweeps; it precomputes once over the full series and
        slices.
        """
        store = self.precompute(close, n_candidates, **param_lists)
        indicator_window = store.window(slice(None), candidate_keys(param_lists))
        return self.simulate(close, indicator_window, n_candidates, **param_lists)


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

    precompute = result.get("precompute")
    if not callable(precompute):
        raise OptimizationSourceError("optimization source must include callable precompute")
    simulate = result.get("simulate")
    if not callable(simulate):
        raise OptimizationSourceError("optimization source must include callable simulate")

    params = _source_params(result.get("params"))
    output_name = result.get("output_name")
    if not isinstance(output_name, str) or output_name not in STRATEGY_ALLOCATION_OUTPUTS:
        raise OptimizationSourceError(
            f"optimization source output_name must be one of {sorted(STRATEGY_ALLOCATION_OUTPUTS)}; "
            f"got {output_name!r}"
        )
    diagnostics = _optional_mapping(result.get("diagnostics", {}), "diagnostics")
    metadata = _optional_mapping(result.get("metadata", {}), "metadata")
    return OptimizationSource(
        precompute=precompute,
        simulate=simulate,
        params=params,
        output_name=output_name,
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
