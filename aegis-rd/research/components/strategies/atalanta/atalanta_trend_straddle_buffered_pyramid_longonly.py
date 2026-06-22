# %% component overview
# Atalanta trend PYRAMID, LONG-ONLY (FORGO convention). Identical signal, vol-sizing, pyramiding ramp
# and no-trade band as atalanta.trendStraddleBufferedPyramid, but downtrends take no position rather
# than a short, and their budget is held as CASH. This is the long-only A/B of the pyramid: aegis-rd-167
# established that on atalanta's diversified non-equity book the short legs are NET value-destructive
# (held-out Sharpe 0.62 L/S -> 0.89 long-only) and largely un-borrowable for retail; this variant carries
# that finding onto the futures substrate so the L/S-vs-long-only lever can be measured directly, holding
# the pyramid ramp grid, EUR base and quarterly-skew ranking identical to the L/S pyramid config.
#
# Gross is taken from the UNCLIPPED, FULL-RAMP signed book (incl. would-be shorts) and reused as the
# divisor, so the long legs keep their natural ramped size and BOTH dropped shorts AND young (un-ramped)
# trends become CASH: the book de-risks toward cash when few names trend up or trends are fresh (gross
# <= 1), instead of re-levering the survivors. ``ramp_steps == 1`` recovers atalanta.trendStraddleBuffered-
# LongOnly EXACTLY (every active long at full ramp, dropped shorts -> cash), so the champion's no-pyramid
# long-only baseline lives inside this grid — a strict generalization, not a competing mechanism.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.trendStraddleBufferedPyramidLongOnly",
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
    """No-pyramid baseline (ramp_steps 1) vs three pyramid ramp lengths, with the buffer.

    entry_band fixed at 0.0 to isolate the pyramiding lever; ramp_steps is the bars of same-direction
    persistence over which a long name builds from zero to full conviction weight.
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
    pyramiding) and larger ramp_steps de-risk young trends and add into maturing ones. (Down-trend ramps
    are still tracked here but their legs are clipped to cash downstream; long ramps are what survive.)
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
    """Long-only inverse-vol conviction weights, PYRAMIDED by trend persistence, FORGO (cash-when-flat).

    Same signal/sizing/ramp as trendStraddleBufferedPyramid but downtrends (score <= 0) take no position.
    The divisor is the full-ramp signed gross (would-be shorts included), so the long legs keep their
    natural size and the dropped-short budget plus the un-matured ramp both become CASH: realized gross
    is the long, ramp-weighted share of the full book, in [0, 1]. At ramp_steps == 1 every active long is
    at ramp 1, reducing this to trendStraddleBufferedLongOnly's gross-from-signed-book normalization.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    raw = np.where(np.abs(score_2d) > entry_band, score_2d / vol, 0.0)
    raw = np.where(np.isfinite(raw), raw, 0.0)
    ramp = _pyramid_ramp(score_2d, entry_band, ramp_steps)
    full_gross = np.abs(raw).sum(axis=1, keepdims=True)  # full-ramp signed gross (incl. would-be shorts)
    pyramided = np.maximum(raw * ramp, 0.0)  # long only: drop short legs; their budget becomes cash
    return pyramided / np.where(full_gross > 0, full_gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized pyramiding long-only absolute-momentum straddle for all candidates."""

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
