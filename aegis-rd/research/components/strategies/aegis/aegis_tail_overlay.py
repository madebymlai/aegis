# %% component overview
# Aegis tail-overlay book — H1 of monetizing-the-tail-sleeve: the allocator's tail-vs-CASH
# weight as a strategy, so the drift band finally has a weight that can drift. aegis.heldHedge
# normalizes the held block to gross 1.0 (fully invested — bands are inert, see tail.yaml);
# this component holds the same inverse-vol SHAPE scaled to a fixed sub-1.0 target
# (``hedge_weight``), remainder in cash. The core is deliberately CASH, not the floor: the run
# isolates the tail leg's own drift, band gating and fixed-fee drag; the floor-blend read
# (delta_theta, blend Sharpe/maxDD) happens in the p2 scratchpad harness on this run's stream.
#
# The monetization mechanics live in the PORTFOLIO band, not here: a tight trim side
# (band_up) harvests the spike — constant-mix sells LVO as it inflates the weight — and a
# wide add side (band_down) re-funds slowly after the spike decays (One River's re-up rule
# expressed as band asymmetry). This component only emits the constant target.
#
# Nested control: hedge_weight 1.0 reproduces aegis.heldHedge byte-for-byte (same shape,
# same gross), validating the new dial before any sub-1.0 cell is read.
# EXPOSURE is deliberately NOT vol-targeted, same reasoning as heldHedge: a tail must be
# present precisely when its own vol spikes.
# Inferred from research/vault/research/monetizing-the-tail-sleeve.md (H1).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "aegis.tailOverlay",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["hedge_weight", "n_benchmark"],
    "output_name": "target_weights",
    "consumes_outputs": ["realized_vol"],
    "defaults": {"hedge_weight": 1.0, "n_benchmark": 0},
    "owns_portfolio": False,
}

# Vol floor: keep the inverse-vol shape finite when a near-flat leg would blow up 1/vol.
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """The H1 overlay weights; the band is a portfolio knob, loop-edited per run.

    ``hedge_weight`` {0.02, 0.05} are the article's pre-registered overlay weights (P2's
    static-drag numbers came from the 0.05 cell). 1.0 is deliberately NOT in the grid - it
    is the heldHedge parity control, exercised in the unit tests, not a candidate.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "hedge_weight": vbt.Param([0.02, 0.05]),
        "n_benchmark": vbt.Param([0]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators': the held inverse-vol shape adds none."""
    return 0


# %% helpers
def _held_weights(vol_2d, n_held, hedge_weight):
    """Inverse-vol SHAPE over the first ``n_held`` legs, gross-normalized to ``hedge_weight``.

    Identical to aegis.heldHedge's shape, scaled so the held block sums to ``hedge_weight``
    and the remainder stays in cash — the target the drift band gates toward. Trailing
    benchmark legs stay NaN (excluded); an all-warmup row collapses to all-zero (cash).
    """

    n_symbols = vol_2d.shape[1]
    out = np.full((vol_2d.shape[0], n_symbols), np.nan, dtype=np.float64)
    if n_held <= 0:
        return out  # misconfigured (all benchmark) -> all excluded; flagged downstream as degenerate
    held = vol_2d[:, :n_held]
    inv = np.where(np.isfinite(held), 1.0 / np.maximum(held, _MIN_VOL), 0.0)
    denom = inv.sum(axis=1, keepdims=True)
    out[:, :n_held] = hedge_weight * inv / np.where(denom > 0, denom, 1.0)
    return out


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized fixed-sub-gross inverse-vol tail book for all candidates."""

    n_symbols = inputs.n_symbols
    T = len(inputs.data.array("Close"))

    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    n_benchmarks = param_lists["n_benchmark"]
    hedge_weights = param_lists["hedge_weight"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        n_held = n_symbols - int(n_benchmarks[ci])
        result_3d[:, ci, :] = _held_weights(vol_3d[:, ci, :], n_held, float(hedge_weights[ci]))

    return result_3d.reshape(T, n_candidates * n_symbols)
