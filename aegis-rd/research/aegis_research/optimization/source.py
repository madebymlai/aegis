"""Optimization source contract.

Signal-side parameter optimization only. A source exposes two execution stages,
a lookback query, and a ``params`` mapping of ``vbt.Param`` axes:

- ``precompute(close, n_candidates, **param_lists) -> IndicatorPrecompute``
  runs each indicator's callable once over the given series, returning a
  candidate-major store sliceable by split range. Run over the **full** series,
  it preserves all available warmup history; candidates whose lookback still
  exceeds that history are invalidated before ranking. Outputs must satisfy the
  ``validate_precompute_no_lookahead`` prefix-equivalence contract: truncating the
  input immediately after a row must not change that row's output values.
- ``simulate(close_window, indicator_window, n_candidates, **param_lists)``
  runs the strategy allocation for one window given the precomputed indicator
  outputs already sliced to that window (the central-metrics step then computes
  portfolio metrics from the returned allocations).
- ``resolve_lookbacks(candidate_params)`` resolves every configured Indicator
  and Strategy lookback from one materialized Candidate's complete scalar
  parameter mapping. Continuous replay queries the complete sampled grid before
  deriving its one common scoring boundary.

The runner's selection sweep precomputes once over the full series and slices per
window so no candidate loses warmup to a short slice. The held-out sweep uses the
same full-series store for the representative candidates.

Limitations carried by this contract:

- Portfolio-side settings are not part of a signal source or Candidate identity.
  They remain fixed run-level policy owned by ``PortfolioConfig`` and are applied
  downstream by the portfolio simulation.

- Hidden params (``vbt.Param(..., hide=True)``) are rejected where the source is
  built. They are excluded from the VBT result index, so candidate identity
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

from research.aegis_research.optimization.precompute import IndicatorPrecompute

OPTIMIZATION_SOURCE_CONTRACT = "aegis.optimization_source.v1"

OPTIMIZATION_PARAM_RESERVED_NAMES = frozenset({"split", "set", "symbol", "metric_name"})


class OptimizationSourceError(ValueError):
    pass


@dataclass(frozen=True)
class OptimizationSource:
    """A signal-side source: two stages, a lookback query, and sweep axes.

    These fields and no more — a source is **signal-side only**. Authoritative
    metrics and portfolio configuration never live on a source: metrics are
    computed downstream by the central-metrics step and the portfolio policy
    owns its own configuration. The fixed field set is what enforces that
    boundary; signal ``params`` names must avoid
    ``OPTIMIZATION_PARAM_RESERVED_NAMES`` (the runner re-checks this at the
    simulation boundary) and ``output_name`` is constrained where the producing
    Component's manifest is built.
    """

    precompute: Callable[..., IndicatorPrecompute]
    simulate: Callable[..., Any]
    resolve_lookbacks: Callable[[Mapping[str, Any]], Mapping[str, int]]
    params: dict[str, vbt.Param]
    output_name: str
    evidence: dict[str, Any]
    diagnostics: dict[str, Any]
    metadata: dict[str, Any]
