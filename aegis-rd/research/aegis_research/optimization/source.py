"""Optimization source contract.

Signal-side parameter optimization only. A source exposes two stages plus a
``params`` mapping of ``vbt.Param`` axes:

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

The runner's selection sweep precomputes once over the full series and slices per
window so no candidate loses warmup to a short slice. The held-out sweep uses the
same full-series store for the representative candidates.

Limitations carried by this contract:

- Portfolio-side params are not part of a signal source. The runner may append
  Aegis-owned portfolio axes (currently the directional drift-band widths) after
  the source is built; the evaluator then keeps those levels in candidate
  identity while the portfolio policy consumes them at simulation time.

- Hidden params (``vbt.Param(..., hide=True)``) are rejected where the source is
  built. They are excluded from the VBT result index, so candidate identity
  would silently collapse across hidden values.

- Component-native optimization composes configured indicator and strategy
  components before this generic runner contract. Legacy playbook optimization
  sources are no longer a forward authoring path.
"""

from __future__ import annotations

from collections.abc import Callable
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
    """A signal-side optimization source: two stages plus the axes to sweep.

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
    params: dict[str, vbt.Param]
    output_name: str
    evidence: dict[str, Any]
    diagnostics: dict[str, Any]
    metadata: dict[str, Any]
