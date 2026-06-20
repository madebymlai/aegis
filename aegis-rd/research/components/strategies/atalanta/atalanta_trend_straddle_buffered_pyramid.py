# %% component overview
# Atalanta trend-straddle + PYRAMIDING (add-to-winners) + turnover buffer. The buffered straddle
# (atalanta.trendStraddleBuffered) sizes each name by signed conviction/vol and gross-normalizes to
# 1.0 every (buffered) rebalance, so the book is always fully invested at CONSTANT gross. This variant
# adds the one shape lever the vault has not tested and the convexity literature ties most directly to
# right-tail skew: PYRAMIDING. Each name's weight ramps from 0 to full over ``ramp_steps`` bars of
# *persistence in the same trend direction*, so total gross floats UP as the live trend set matures and
# DOWN when trends are fresh or absent. Exposure is therefore largest exactly when moves have already
# extended (convex - manufactures the right tail) and smallest in chop, the opposite of constant gross.
#
# Why this lever and not the others in [[what-makes-a-trend-sleeve-convex]]: speed/vol-window/short-side
# are already params; magnitude response is already how trendStraddle sizes (score/vol, not sign); and
# the 2026-06-14 sweep already KILLED sigmoid response and vol-targeting (both sell convexity on the
# non-equity book) and KEPT the turnover buffer. Pyramiding is path/persistence-based position building,
# distinct from all three and untested here. Sources: NilssonHedge "continuously adding exposure to an
# existing trend position ... increasingly exposed to a trend with strong positive drifts" (raises skew);
# Concretum/Mulvaney "pyramiding into winners" as a core ingredient of a ~+5.98 trade-skew, 25-yr program.
#
# ``ramp_steps == 1`` recovers atalanta.trendStraddleBuffered EXACTLY (every active name is at full ramp,
# so gross == 1 and the weights are identical) - the no-pyramid baseline lives inside the grid, making
# this a strict generalization rather than a competing mechanism.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.trendStraddleBufferedPyramid",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["entry_band", "buffer_band", "ramp_steps"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"entry_band": 0.0, "buffer_band": 0.20, "ramp_steps": 1},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (see trendStraddle).
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """No-pyramid baseline (ramp_steps 1) vs three pyramid ramp lengths, with/without the buffer.

    entry_band fixed at 0.0 to isolate the pyramiding lever; ramp_steps is the bars of same-direction
    persistence over which a name builds from zero to full conviction weight.
    """

    return {
        "entry_band": vbt.Param([0.0]),
        "buffer_band": vbt.Param([0.20]),
        "ramp_steps": vbt.Param([1, 21, 63]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators': the persistence counter starts from the first scored bar."""
    return 0


# %% helpers
def _pyramid_ramp(score_2d, entry_band, ramp_steps):
    """Per-name 0..1 multiplier ramping in over ``ramp_steps`` bars of same-direction trend persistence.

    Direction is the entry-gated sign of the trend score; the persistence counter increments while the
    direction holds, resets to 1 on a direction flip, and to 0 when flat (|score| <= entry_band or NaN).
    ramp = min(count, ramp_steps) / ramp_steps, so ramp_steps == 1 yields ramp 1 whenever active (no
    pyramiding) and larger ramp_steps de-risk young trends and add into maturing ones.
    """

    T, n = score_2d.shape
    steps = max(int(ramp_steps), 1)
    direction = np.where(
        np.isfinite(score_2d) & (np.abs(score_2d) > entry_band), np.sign(score_2d), 0.0
    )
    ramp = np.zeros((T, n))
    count = np.zeros(n)
    prev = np.zeros(n)
    for t in range(T):
        d = direction[t]
        same = (d != 0.0) & (d == prev)
        count = np.where(same, count + 1.0, np.where(d != 0.0, 1.0, 0.0))
        ramp[t] = np.minimum(count, steps) / steps
        prev = d
    return ramp


def _apply_buffer(weights, band):
    """No-trade band: carry the held book until its L1 drift from the new target exceeds ``band``.

    Self-contained copy of the buffered straddle's band (components are loaded as standalone units);
    band 0.0 is a pass-through. Note the carried book keeps its (floating) gross, which the pyramiding
    weights already bound to <= 1.0, so the band never breaches the gross cap.
    """

    if band <= 0.0:
        return weights
    out = weights.copy()
    held = weights[0].copy()
    for t in range(1, len(weights)):
        if np.abs(weights[t] - held).sum() > band:
            held = weights[t].copy()
        out[t] = held
    return out


def _candidate_weights(score_2d, vol_2d, entry_band, ramp_steps):
    """Signed inverse-vol conviction weights, PYRAMIDED by trend persistence, gross floating to <= 1.0.

    The reference scale is the *full-ramp* gross (what the gross would be with every active name at
    ramp 1); dividing the ramped book by it makes the realized gross the conviction-weighted mean ramp
    over active names, in [0, 1]: the book de-risks while trends are young and approaches gross 1 as
    they mature. At ramp_steps == 1 every active name is at ramp 1, so this reduces to the buffered
    straddle's gross-1 normalization exactly.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    raw = np.where(np.abs(score_2d) > entry_band, score_2d / vol, 0.0)
    raw = np.where(np.isfinite(raw), raw, 0.0)
    ramp = _pyramid_ramp(score_2d, entry_band, ramp_steps)
    full_gross = np.abs(raw).sum(axis=1, keepdims=True)
    pyramided = raw * ramp
    return pyramided / np.where(full_gross > 0, full_gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized pyramiding long/short absolute-momentum straddle for all candidates."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    entry_bands = param_lists["entry_band"]
    buffer_bands = param_lists["buffer_band"]
    ramp_steps_list = param_lists["ramp_steps"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        w = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], float(entry_bands[ci]), int(ramp_steps_list[ci])
        )
        result_3d[:, ci, :] = _apply_buffer(w, float(buffer_bands[ci]))

    return result_3d.reshape(T, n_candidates * n_symbols)
