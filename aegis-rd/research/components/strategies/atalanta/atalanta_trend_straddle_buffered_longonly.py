# %% component overview
# Atalanta trend-straddle + turnover buffer, LONG-ONLY (FORGO convention). Identical signal,
# vol-sizing and no-trade band as atalanta.trendStraddleBuffered, but downtrends take no
# position rather than a short, and their budget is held as CASH (gross taken from the unclipped
# signed book, so the long legs keep their natural size; gross ≤ 1, de-risking toward cash when
# few names trend up). This is the production variant of the champion: on atalanta's non-equity
# universe the short legs are net value-destructive and largely un-borrowable for retail (IBKR
# probe 2026-06-16), while the crisis convexity (qskew) comes from the long legs. FORGO beats
# gross-1 re-normalization on Sharpe/UPI/qskew and halves the tail drawdown (full-sample floor
# re-test, aegis-rd-167). direction must be `longonly` (all weights ≥ 0).

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.trendStraddleBufferedLongOnly",
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
    """No warmup beyond the indicators'."""
    return 0


# %% helpers
def _candidate_weights(score_2d, vol_2d, entry_band):
    """Long-only vol-scaled conviction weights, FORGO convention (cash-when-flat).

    Same signal/sizing as trendStraddleBuffered but downtrends (score ≤ 0) take no position
    rather than a short. Gross is taken from the UNCLIPPED (signed) book and reused as the
    divisor, so the long legs keep their natural size and the dropped-short budget becomes CASH:
    when few names trend up the book de-risks toward cash (gross ≤ 1) instead of re-levering the
    survivors to gross 1.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    raw = np.where(np.abs(score_2d) > entry_band, score_2d / vol, 0.0)
    raw = np.where(np.isfinite(raw), raw, 0.0)
    gross = np.abs(raw).sum(axis=1, keepdims=True)  # pre-clip gross (incl. would-be shorts)
    raw = np.maximum(raw, 0.0)  # long only: drop short legs; their budget becomes cash
    return raw / np.where(gross > 0, gross, 1.0)


def _apply_buffer(weights, band):
    """No-trade band: carry the held book until its L1 drift from the new target exceeds ``band``."""

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
    """Vectorized buffered long-only absolute-momentum straddle for all candidates."""

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
