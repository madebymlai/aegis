# %% playbook overview
# Optimization-source playbook example (forward path for issue #31).
# Returns an `aegis.optimization_source.v1` contract: one parameterized pipeline
# plus a `params` mapping built from `vbt.Param`. Aegis wraps the pipeline in
# `vbt.cv_split`, enumerates parameter combinations natively, selects winners
# by the configured ranking metric on the selection set, and ranks them on the
# held-out set. The playbook does not compose its own candidate IDs and does
# not consume external indicator playbooks; everything the pipeline needs is
# computed inline from Close plus VBT params.

# %% imports
from vectorbtpro import vbt

# %% define playbook metadata
PLAYBOOK_MANIFEST = {
    "family": "strategies",
    "id": "example_ma_optimization",
    "version": "1.0.0",
    "stages": ["strategies"],
    "accepted_inputs": ["Close"],
    "result_schema": "aegis.optimization_source.v1",
}
PLAYBOOK_CALLABLE = "build_source"


# %% main compute
def build_source(inputs):
    """Return an aegis.optimization_source.v1 contract for an MA-cross sweep."""

    def pipeline(close, fast_window, slow_window):
        fast = close.rolling(fast_window, min_periods=1).mean()
        slow = close.rolling(slow_window, min_periods=1).mean()
        entries = (fast > slow).fillna(False)
        exits = (fast < slow).fillna(False)
        return entries, exits

    return {
        "contract": "aegis.optimization_source.v1",
        "kind": "optimization_source",
        "pipeline": pipeline,
        "params": {
            "fast_window": vbt.Param([5, 10, 20]),
            "slow_window": vbt.Param([50, 100, 200], condition="x > fast_window"),
        },
    }


# %% playground notes
# Playground notes:
# - The pipeline is invoked once per (split, set, parameter row) by VBT during
#   execution. Aegis owns portfolio simulation and central metrics; the
#   pipeline returns only entries/exits.
# - Use `vbt.Param(..., level=...)` to tie parameters that should vary together
#   instead of forming a Cartesian product.
# - Use `vbt.Param(..., condition=...)` to drop invalid combinations (above,
#   `slow_window` is only valid when greater than `fast_window`).
# - For random/lazy search, set `optimization.search: random`,
#   `optimization.random_subset: N`, and `optimization.seed: ...` in the run
#   config; the sampled parameter rows are persisted under
#   `execution.sampled_rows` in strategy_run.json.
