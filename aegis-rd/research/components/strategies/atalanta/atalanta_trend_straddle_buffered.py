# %% component overview
# Atalanta trend-straddle v2 + TURNOVER BUFFER (no-trade band). Identical vol-scaled,
# conviction-weighted long/short TSMOM as atalanta.trendStraddle, then a portfolio-level
# no-trade band: the book is only re-set to the new target when the L1 weight drift from the
# currently-held book exceeds ``buffer_band``; otherwise it is carried. This is the one
# Sharpe lever that the 2026-06-14 exa sweep + our own data both confirm *raises* Sharpe
# WHILE preserving/raising convexity (vol-targeting, efficiency-ratio sizing and sigmoid
# response all SELL convexity on a non-equity book and were rejected; breadth/cap throttles
# hurt empirically). It works by removing the high-frequency micro-rebalancing whipsaw that
# bleeds fees and chops positions right before continuation — letting winners run (raises
# right skew) and cutting cost drag (raises Sharpe). Baltas-Kosowski (2015): efficient
# trading reduces turnover >1/3 without performance degradation; here, with improvement.
#
# Validated 2026-06-14 (research/vault/runs/atalanta/2026-06-14.md): on the live London
# Tier-1 book, band 0.20 on the slow2 ensemble lifts Sharpe +0.48->+0.61 and qskew
# +2.33->+2.44 at flat crisis-conditional, halving turnover. Drop-in for atalanta.trendStraddle.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.trendStraddleBuffered",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["entry_band", "buffer_band"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"entry_band": 0.0, "buffer_band": 0.20},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (see trendStraddle).
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """Entry dead-zone (annualized score) × no-trade band (L1 weight drift to trigger a re-set)."""

    return {
        "entry_band": vbt.Param([0.0, 0.05]),
        "buffer_band": vbt.Param([0.0, 0.10, 0.20, 0.30]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators': the buffered straddle adds none."""
    return 0


# %% helpers
def _candidate_weights(score_2d, vol_2d, entry_band):
    """Signed vol-scaled conviction weights for one candidate, gross-normalized to 1.0."""

    vol = np.maximum(vol_2d, _MIN_VOL)
    raw = np.where(np.abs(score_2d) > entry_band, score_2d / vol, 0.0)
    raw = np.where(np.isfinite(raw), raw, 0.0)
    gross = np.abs(raw).sum(axis=1, keepdims=True)
    return raw / np.where(gross > 0, gross, 1.0)


def _apply_buffer(weights, band):
    """No-trade band: carry the held book until its L1 drift from the new target exceeds ``band``.

    ``weights`` rows are each gross-normalized to 1.0, so a carried (held) row stays gross-1 —
    the band never breaches the gross cap. band 0.0 is a pass-through (re-set every bar).
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


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized buffered long/short absolute-momentum straddle for all candidates."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    entry_bands = param_lists["entry_band"]
    buffer_bands = param_lists["buffer_band"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        w = _candidate_weights(score_3d[:, ci, :], vol_3d[:, ci, :], float(entry_bands[ci]))
        result_3d[:, ci, :] = _apply_buffer(w, float(buffer_bands[ci]))

    return result_3d.reshape(T, n_candidates * n_symbols)
