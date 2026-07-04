# %% component overview
# Aegis tail-harvest book — H2 of monetizing-the-tail-sleeve: the Bhansali profit-multiple
# harvest stacked on the H1 drift-band base (aegis.tailOverlay + the B2' 0.01/0.015 band).
# Target weight is ``hedge_weight`` as in tailOverlay, except while the leg's spike_ratio
# (Close / rolling ref_window low, the ETP's cost-basis proxy) marks at or above
# ``harvest_multiple``: then the target drops to ``floor_frac x hedge_weight`` — sell the
# spike down TOWARD A FLOOR, never to zero (the double-dip guardrail: a residual position
# stays live for a second leg down). When the ratio decays back below the multiple the
# target returns to hedge_weight and the band's slow re-fund side (band_down) paces the
# re-buy — One River's re-up rule, already in the base. The trigger is the position's OWN
# path (no external VIX level), per the article's Volmageddon guardrail.
#
# harvest_multiple 0.0 disables the harvest entirely and reproduces aegis.tailOverlay
# byte-for-byte at the same hedge_weight (nested control; the multiplier branch is skipped,
# not multiplied by 1, so parity is exact).
# Inferred from research/vault/research/monetizing-the-tail-sleeve.md (H2).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "aegis.tailHarvest",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["hedge_weight", "harvest_multiple", "floor_frac", "n_benchmark"],
    "output_name": "target_weights",
    "consumes_outputs": ["realized_vol", "spike_ratio"],
    "defaults": {"hedge_weight": 1.0, "harvest_multiple": 0.0, "floor_frac": 0.4, "n_benchmark": 0},
    "owns_portfolio": False,
}

# Vol floor: keep the inverse-vol shape finite when a near-flat leg would blow up 1/vol.
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """H2 grid: the multiple is the lever; weight spans H1's cells; the floor is pinned.

    ``harvest_multiple`` 0.0 is the H1/B2' nested control (no harvest). 2.0 fires on
    Feb-2018-scale spikes and COVID; 3.0 is Bhansali's canonical lower band (COVID-only on
    LVO's history); 5.0 nearly never (a near-control probing the trigger's tail).
    ``floor_frac`` 0.4 keeps 40% of the target through the harvest state — sell toward a
    floor, never to zero (pre-registered, not swept; sweep only if H2 keeps).
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "hedge_weight": vbt.Param([0.02, 0.05]),
        "harvest_multiple": vbt.Param([0.0, 2.0, 3.0, 5.0]),
        "floor_frac": vbt.Param([0.4]),
        "n_benchmark": vbt.Param([0]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators': shape and harvest state add none."""
    return 0


# %% helpers
def _held_weights(vol_2d, n_held, hedge_weight):
    """Inverse-vol SHAPE over the first ``n_held`` legs, gross-normalized to ``hedge_weight``.

    Identical to aegis.tailOverlay's helper: NaN = excluded trailing benchmark legs; an
    all-warmup row collapses to all-zero (cash).
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
    """Vectorized banded tail book with a per-leg profit-multiple harvest state."""

    n_symbols = inputs.n_symbols
    T = len(inputs.data.array("Close"))

    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    ratio_3d = inputs.indicators["spike_ratio"].reshape(T, n_candidates, n_symbols)
    n_benchmarks = param_lists["n_benchmark"]
    hedge_weights = param_lists["hedge_weight"]
    multiples = param_lists["harvest_multiple"]
    floor_fracs = param_lists["floor_frac"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        n_held = n_symbols - int(n_benchmarks[ci])
        weights = _held_weights(vol_3d[:, ci, :], n_held, float(hedge_weights[ci]))
        multiple = float(multiples[ci])
        if multiple > 0.0:
            ratio = ratio_3d[:, ci, :n_held]
            in_harvest = np.isfinite(ratio) & (ratio >= multiple)
            scale = np.where(in_harvest, float(floor_fracs[ci]), 1.0)
            weights[:, :n_held] = weights[:, :n_held] * scale
        result_3d[:, ci, :] = weights

    return result_3d.reshape(T, n_candidates * n_symbols)
