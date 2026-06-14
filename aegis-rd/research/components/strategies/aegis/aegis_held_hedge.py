# %% component overview
# Aegis held-hedge tail sleeve — the standalone target-tier strategy of the roster
# (research/vault/research/the-tiered-strategy-roster.md). It is the SLEEVE itself, not its
# overlay on a floor: combining sleeves into a book is the future allocator's job, so aegis
# carries no atalanta/demeter logic and is built and scored on its own, exactly as the trend
# and carry poles are. The book is a fixed-weight, inverse-vol-balanced hold of the tail
# instrument(s) — Regime A: VOOL, the EUR UCITS VIX-futures ETF (the "UCITS VIXY") — held
# CONSTANT every bar. Holding a fixed weight IS the monetization rule: the continuous
# rebalance sells the convex leg as it spikes (and, inside a future allocator, buys the
# falling core at the trough). EXPOSURE is fixed at the gross cap and is deliberately NOT
# vol-targeted: a tail must be present precisely when its own vol spikes, so de-risking it on
# a vol-target would cut the convexity the sleeve exists to deliver (this is why demeter's
# vol-target stage is dropped here). Only the cross-sectional SHAPE uses inverse vol, so a
# multi-leg basket is risk-balanced; for a single leg the shape is trivially 1.0.
#
# Trailing ``n_benchmark`` symbols are MEASUREMENT-ONLY (e.g. SPY for the benchmark-relative
# convexity / down-capture metrics) and are EXCLUDED from the held book via the NaN = excluded
# convention, so the held weights and the metric benchmark live in one panel without the
# benchmark polluting the allocation.
#
# Standalone at gross 1.0 over the single VOOL leg this run is the raw spike-versus-bleed
# stream the article asks to measure directly on our own harness; the floor blend and the
# "Target earns its bleed" relative gate wait for the allocator.
# Inferred from research/vault/research/the-ucits-constrained-tail-sleeve.md (Regime A, h1).
# See research/vault/runs/aegis/2026-06-14.md.

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "aegis.heldHedge",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["n_benchmark"],
    "output_name": "target_weights",
    "consumes_outputs": ["realized_vol"],
    "defaults": {"n_benchmark": 0},
    "owns_portfolio": False,
}

# Vol floor: keep the inverse-vol shape finite when a near-flat leg would blow up 1/vol.
_MIN_VOL = 0.01


# %% helpers
def _held_weights(vol_2d, n_held):
    """Fixed inverse-vol SHAPE over the first ``n_held`` legs, gross-normalized to 1.0.

    The remaining (trailing, benchmark-only) legs are left NaN — the NaN = excluded
    convention keeps them out of the held book. A row with no finite vol among the held
    legs (warmup) collapses to an all-zero held block (cash, not an error). The weights
    are identical every bar by construction, which is the continuous-rebalance / fixed-
    weight monetization rule the simulator then enforces against price drift.
    """

    n_symbols = vol_2d.shape[1]
    out = np.full((vol_2d.shape[0], n_symbols), np.nan, dtype=np.float64)
    if n_held <= 0:
        return out  # misconfigured (all benchmark) -> all excluded; flagged downstream as degenerate
    held = vol_2d[:, :n_held]
    inv = np.where(np.isfinite(held), 1.0 / np.maximum(held, _MIN_VOL), 0.0)
    denom = inv.sum(axis=1, keepdims=True)
    out[:, :n_held] = inv / np.where(denom > 0, denom, 1.0)  # all-warmup row -> all-zero (cash)
    return out


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized fixed-weight inverse-vol held-hedge book for all candidates."""

    n_symbols = inputs.n_symbols
    T = len(inputs.data.array("Close"))

    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    n_benchmarks = param_lists["n_benchmark"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        n_held = n_symbols - int(n_benchmarks[ci])
        result_3d[:, ci, :] = _held_weights(vol_3d[:, ci, :], n_held)

    return result_3d.reshape(T, n_candidates * n_symbols)
