# %% component overview
# Aegis tail-throttle book — H3 of monetizing-the-tail-sleeve: the expected-carry throttle
# on the H1 drift-band base. Target weight is ``hedge_weight`` while the leg's trailing
# momentum (aegis.trail_momentum, the price-only carry-state proxy) reads stress
# (momentum > 0), and ``calm_frac x hedge_weight`` while it reads calm contango
# (momentum <= 0, or warmup NaN - calm is the conservative default state). The floor is
# NEVER zero: always-on in the sense that matters (SOA late-gate + CalPERS guardrails in
# the article); the throttle only decides how much bleed to pay while nothing is
# happening. This is a carry state, not a crash predictor - the counter-evidence (AQR fn14
# / Tummala) rejects turn-on timing, and the wrapper already owns the fast spike trigger.
# Shape follows QuantPedia's "Robust VIXY Models" conditional long-vol allocation: binary
# state, hold-or-floor, no forecast.
#
# calm_frac 1.0 disables the throttle and reproduces aegis.tailOverlay byte-for-byte at
# the same hedge_weight (nested control; the multiplier branch is skipped, not applied).
# Inferred from research/vault/research/monetizing-the-tail-sleeve.md (H3).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "aegis.tailThrottle",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["hedge_weight", "calm_frac", "n_benchmark"],
    "output_name": "target_weights",
    "consumes_outputs": ["realized_vol", "trail_momentum"],
    "defaults": {"hedge_weight": 1.0, "calm_frac": 1.0, "n_benchmark": 0},
    "owns_portfolio": False,
}

# Vol floor: keep the inverse-vol shape finite when a near-flat leg would blow up 1/vol.
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """H3 grid: the champion weight, throttled or not; calm_frac loop-edits per run.

    ``hedge_weight`` is pinned to the locked champion 0.05 (H1/H2 showed w-proportionality;
    the 0.02 read adds nothing the keep/kill needs). ``calm_frac`` 1.0 is the nested
    control (= the locked tail_band B2' cell); the active fractions are pinned per launch
    in the config so the 3-cell mom_window sweep fits the store's 3 persisted roles.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "hedge_weight": vbt.Param([0.05]),
        "calm_frac": vbt.Param([1.0]),
        "n_benchmark": vbt.Param([0]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators': shape and throttle state add none."""
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
    """Vectorized banded tail book with a per-leg carry-state throttle."""

    n_symbols = inputs.n_symbols
    T = len(inputs.data.array("Close"))

    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    mom_3d = inputs.indicators["trail_momentum"].reshape(T, n_candidates, n_symbols)
    n_benchmarks = param_lists["n_benchmark"]
    hedge_weights = param_lists["hedge_weight"]
    calm_fracs = param_lists["calm_frac"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        n_held = n_symbols - int(n_benchmarks[ci])
        weights = _held_weights(vol_3d[:, ci, :], n_held, float(hedge_weights[ci]))
        calm_frac = float(calm_fracs[ci])
        if calm_frac != 1.0:
            mom = mom_3d[:, ci, :n_held]
            in_stress = np.isfinite(mom) & (mom > 0.0)
            scale = np.where(in_stress, 1.0, calm_frac)
            weights[:, :n_held] = weights[:, :n_held] * scale
        result_3d[:, ci, :] = weights

    return result_3d.reshape(T, n_candidates * n_symbols)
