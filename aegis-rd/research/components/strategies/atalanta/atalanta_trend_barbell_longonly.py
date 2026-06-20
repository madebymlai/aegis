# %% component overview
# Atalanta BARBELL trend, long-only FORGO. Builds a long-only forgo sub-book at each of the two
# barbell horizons (fast + slow trend scores from atalanta.trend_score_barbell) and averages the
# two weight matrices (sub-portfolio ensemble — preserves the fast horizon's ability to flip a
# name to cash in a crash even while the slow horizon is still long), then applies the turnover
# buffer. FORGO convention per horizon: gross from the unclipped signed book, drop short legs to
# cash (gross ≤ 1). Convexity tilt vs the single-252 pole (higher qskew at a small Sharpe cost) —
# the barbell beats the full 63/126/252 ensemble (medium redundant). See aegis-rd-167.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.trendBarbellLongOnly",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["entry_band", "buffer_band"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score_fast", "trend_score_slow", "realized_vol"],
    "defaults": {"entry_band": 0.0, "buffer_band": 0.20},
    "owns_portfolio": False,
}

_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """Entry dead-zone × no-trade band."""

    return {
        "entry_band": vbt.Param([0.0, 0.05]),
        "buffer_band": vbt.Param([0.0, 0.10, 0.20, 0.30]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators'."""
    return 0


# %% helpers
def _forgo(score_2d, vol_2d, entry_band):
    """Long-only forgo weights for one horizon: gross from the unclipped signed book, drop shorts to cash."""

    vol = np.maximum(vol_2d, _MIN_VOL)
    raw = np.where(np.abs(score_2d) > entry_band, score_2d / vol, 0.0)
    raw = np.where(np.isfinite(raw), raw, 0.0)
    gross = np.abs(raw).sum(axis=1, keepdims=True)  # pre-clip gross
    raw = np.maximum(raw, 0.0)  # long only; dropped-short budget -> cash
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
    """Vectorized barbell long-only forgo ensemble for all candidates."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    fast = inputs.indicators["trend_score_fast"].reshape(T, n_candidates, n_symbols)
    slow = inputs.indicators["trend_score_slow"].reshape(T, n_candidates, n_symbols)
    vol = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    entry_bands = param_lists["entry_band"]
    buffer_bands = param_lists["buffer_band"]

    result = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        wf = _forgo(fast[:, ci, :], vol[:, ci, :], float(entry_bands[ci]))
        ws = _forgo(slow[:, ci, :], vol[:, ci, :], float(entry_bands[ci]))
        result[:, ci, :] = _apply_buffer(0.5 * (wf + ws), float(buffer_bands[ci]))

    return result.reshape(T, n_candidates * n_symbols)
