# %% component overview
# Demeter carry allocator — the fix for the credit pole's inert signal. The
# credit SPREAD is a TIME-SERIES (common-factor) signal: demeter_eu.credit_carry broadcasts
# one richness scalar to every leg. carryStraddle gross-normalizes w_i ∝ score/vol_i, which
# by the Baltas-Kosowski identity (cross-sectional weights = time-series weights − the
# cross-sectional mean) SUBTRACTS a common score to zero — so the signal washed out and the
# book degenerated to a static always-on inverse-vol credit book (the verified bug). The
# routing error is the cause: a time-series signal belongs on the EXPOSURE axis, not the
# cross-sectional weighting axis (Man two-step: risk allocation × exposure scaling).
#
# This allocator routes the SAME strong spread signal correctly:
#   - SHAPE (who gets what, cross-sectional)  = inverse-vol across the legs, gross-normalized
#     to 1.0 — the risk-balanced base. The spread no longer touches the shape, so it can't be
#     annihilated.
#   - EXPOSURE (how much to deploy, time-series) = a smooth vol-target scaled by the spread
#     RICHNESS, capped at gross 1.0 (UCITS: long-only, no leverage). vol-target de-risks when
#     realized vol spikes (the drawdown brake the always-on book lacked); the richness lean
#     (carry_gain) leans INTO credit when the spread is rich vs its own history and OUT when
#     thin. carry_gain = 0 recovers a pure vol-target (the no-timing baseline for the A/B).
# Output gross = exposure ≤ 1.0, all weights ≥ 0, so Exposure Validation passes it unsized.
# Simulation runs on total-return Close so the book collects the carry it holds.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.carry",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["vol_target", "carry_gain"],
    "output_name": "target_weights",
    "consumes_outputs": ["carry_score", "realized_vol"],
    "defaults": {"vol_target": 0.10, "carry_gain": 0.0},
    "owns_portfolio": False,
}

# Vol floor: keep the inverse-vol weight and the vol-target ratio finite when a near-flat
# leg or a calm book would otherwise blow the reciprocal up.
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """Return VBT-native params for the exposure stage.

    ``vol_target`` is the annualized book-vol the exposure scales toward (capped at gross
    1.0); ``carry_gain`` is the spread-richness lean exponent (0 = pure vol-target, no carry
    timing; higher = lean harder into rich credit and out of thin credit).
    """

    return {
        "vol_target": vbt.Param([0.06, 0.10, 0.15]),
        "carry_gain": vbt.Param([0.0, 1.0, 2.0]),
    }


# %% helpers
def _weights(score_2d, vol_2d, vol_target, carry_gain):
    """Inverse-vol SHAPE × vol-targeted, richness-leaned EXPOSURE for one candidate.

    shape_i = (1/vol_i) / Σ(1/vol_j)  (cash on a fully-warmup row, no error).
    richness = mean across legs of the common spread carry_score (~1 at neutral, ≥ 0).
    exposure = min( (vol_target / σ_book) · richness^carry_gain , 1.0 ),  σ_book = Σ shape_i·vol_i.
    w_i = shape_i · exposure  →  gross = exposure ≤ 1.0, long-only.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    inv = np.where(np.isfinite(vol_2d), 1.0 / vol, 0.0)  # warmup vol NaN → 0 weight
    denom = inv.sum(axis=1, keepdims=True)
    shape = inv / np.where(denom > 0, denom, 1.0)  # rows with no finite vol → all-zero (cash)

    sigma_book = (shape * vol).sum(axis=1, keepdims=True)  # comonotone approx (legs ~0.8 corr)

    # Common spread richness across the legs; a fully-NaN warmup row → 0 (cash, no timing).
    richness = np.nanmean(np.where(np.isfinite(score_2d), score_2d, np.nan), axis=1, keepdims=True)
    richness = np.where(np.isfinite(richness), np.maximum(richness, 0.0), 0.0)
    lean = np.power(richness, carry_gain) if carry_gain != 0.0 else np.ones_like(richness)

    exposure = np.minimum(vol_target / np.maximum(sigma_book, _MIN_VOL) * lean, 1.0)
    return shape * exposure


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized vol-targeted exposure credit book for all candidates."""

    n_symbols = inputs.n_symbols
    T = len(inputs.data.array("Close"))

    score_3d = inputs.indicators["carry_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    vol_targets = param_lists["vol_target"]
    carry_gains = param_lists["carry_gain"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _weights(
            score_3d[:, ci, :], vol_3d[:, ci, :],
            float(vol_targets[ci]), float(carry_gains[ci]),
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
