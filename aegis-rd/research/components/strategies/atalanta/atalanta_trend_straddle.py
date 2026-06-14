# %% component overview
# Atalanta trend-straddle v2: vol-scaled, conviction-weighted long/short TSMOM.
# Per name the weight is w_i ∝ trend_score_i / realized_vol_i (dead-zoned, then
# gross-normalized to 1.0). The signed-score numerator IS conviction weighting —
# a name just past a zero crossing has a small |score| and so a small position,
# which soft-damps the V-recovery whipsaw that wrecked the crude sign-flip v1;
# dividing by realized vol risk-balances the book (Moskowitz-Ooi-Pedersen), so a
# quiet UUP and a wild XLE take comparable risk. Net exposure stays free to swing
# directionally (net long in broad uptrends, net SHORT in broad downtrends) — the
# convex straddle payoff. Goal vs v1: keep the defensive convexity while
# restoring positive return + positive skew so it reads as the floor's long-gamma
# TREND pole, not a bleeding tail hedge.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.trendStraddle",
    "version": "2.0.0",
    "input_names": ["Close"],
    "param_names": ["entry_band"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"entry_band": 0.0},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped, so a
# near-flat series cannot absorb the whole book.
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """Return VBT-native params for the trend entry dead-zone (annualized score)."""

    return {
        # |trend_score| inside the band is cash; a positive band requires a
        # minimum trend strength on either side before taking a position.
        "entry_band": vbt.Param([0.0, 0.02, 0.05]),
    }


# %% helpers
def _candidate_weights(score_2d, vol_2d, entry_band):
    """Signed vol-scaled conviction weights for one candidate, gross-normalized to 1.0.

    ``w_i ∝ score_i / max(vol_i, floor)`` for names past the dead-zone, else 0.
    Warmup NaN scores/vols are not > entry_band (and divide to NaN), so they fall
    through to 0.0 (cash). A fully neutral row normalizes to cash — no error.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    raw = np.where(np.abs(score_2d) > entry_band, score_2d / vol, 0.0)
    raw = np.where(np.isfinite(raw), raw, 0.0)
    gross = np.abs(raw).sum(axis=1, keepdims=True)
    return raw / np.where(gross > 0, gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized vol-scaled long/short absolute-momentum straddle for all candidates."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    entry_bands = param_lists["entry_band"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], float(entry_bands[ci])
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
