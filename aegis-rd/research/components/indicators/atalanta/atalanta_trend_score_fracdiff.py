# %% component overview
# Atalanta trend score, FRACTIONAL-DIFFERENCE variant - the momentum signal of Chitsiripanich, Paolella,
# Polak & Walker ("Momentum Without Crashes", 2022), which replaces the endpoint difference of classical
# momentum (logP_t - logP_{t-lb}, only two prices) with a fractional-difference filter that weights ALL
# prices in the window:
#     signal_raw_t = sum_{k=0}^{lb} w_k(d) * logP_{t-k},   w_0 = 1,  w_k = -w_{k-1} * (d-k+1)/k
# The frac-diff weights (Hosking / Lopez de Prado) have w_0 > 0 and alternating, decaying tail weights,
# so the signal "coherently combines momentum and reversal": recent moves get positive weight, older
# moves a decaying negative (reversal) weight. Because sum_k w_k = (1-1)^d = 0, signal_raw is a
# return-like zero-sum combination (no price-level drift), preserving memory while being (near-)
# stationary - the stationarity-vs-memory balance a pure lb-return over-differences away.
#
# SCALE-MATCHED TO THE CHAMPION (so the enter/exit bands stay calibrated, no confound). For a PURE
# linear log-trend (slope m/bar), signal_raw = m * K(d,lb) with K = -sum_k k*w_k, so the frac-diff
# implied per-bar slope is signal_raw / K, and we annualize it EXACTLY like atalanta.trend_score_regress:
#     trend_score = exp(252 * signal_raw / K(d,lb)) - 1
# Thus on a clean trend the frac-diff score EQUALS the champion score at any d - the two differ only by
# how frac-diff reweights a NOISY path (its momentum+reversal shape), which is precisely the effect
# under test. A drop-in for trend_score (same output name and units); pure signal swap.
#
# HONEST PRIOR ([[budgeting-the-divergent-seat]] / design research). It does NOT nest the champion (no d
# equals the OLS slope), so this is a scale-matched comparison, not a nested control. And Kim & Kim
# (2024, "A note on the fractional momentum strategy") show the frac-diff edge holds under WEEKLY
# rebalancing but goes INFERIOR to plain momentum as rebalancing SLOWS - and this sleeve is a slow,
# drift-band, ~5-fills/year book, so the edge is predicted to be absent here. This run tests that
# directly on our book rather than assuming it. Lopez de Prado's d is typically 0.1-0.5 for equity
# indices (min-d for stationarity); we sweep the memory-preserving mid-range. Speed co-swept (unlocked)
# since a new signal logic may have a different optimal lookback than the raw slope's 189.
# Strictly CAUSAL trailing window; windowed compute incurred once (the windowed-compute-in-indicator rule).

# %% imports
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.trend_score_fracdiff",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["lookback", "frac_d"],
    "output_names": ["trend_score"],
    "defaults": {"lookback": 189, "frac_d": 0.5},
}


# %% parameter space
def param_space():
    """Co-sweep trend SPEED and the fractional-difference order d.

    ``lookback`` spans the full {21..252} range (unlocked: a frac-diff signal may peak at a different
    speed than the raw slope's 189). ``frac_d`` spans the memory-preserving band {0.3, 0.5, 0.7} - low
    d keeps more memory (closer to the raw price level / slow trend), high d differences more (closer to
    a fast return); the reversal tail of the kernel grows with the window.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "lookback": vbt.Param([21, 42, 63, 126, 189, 252]),
        "frac_d": vbt.Param([0.3, 0.5, 0.7]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars for the frac-diff score: the fixed-width filter window length."""
    return int(params["lookback"])


# %% helpers
def _fracdiff_weights(d, window):
    """Fixed-width fractional-difference weights w_0..w_window: w_0=1, w_k=-w_{k-1}(d-k+1)/k."""

    w = np.empty(window + 1, dtype=np.float64)
    w[0] = 1.0
    for k in range(1, window + 1):
        w[k] = -w[k - 1] * (d - k + 1) / k
    return w


def _score_fracdiff(log_close, window, d):
    """Scale-matched annualized frac-diff momentum score, per symbol."""

    T, n_symbols = log_close.shape
    out = np.full((T, n_symbols), np.nan)
    if T > window and window >= 1:
        w = _fracdiff_weights(d, window)  # (window+1,), w[k] multiplies logP[t-k]
        k_grid = np.arange(window + 1, dtype=np.float64)
        K = -float(k_grid @ w)  # pure-trend scale: signal_raw = m * K
        wins = sliding_window_view(log_close, window + 1, axis=0)  # (T-window, n, window+1)
        # signal_raw_t = sum_k w[k] logP[t-k]; with wins[i,:,j]=logP[i+j] and t=i+window -> use reversed w
        signal_raw = wins @ w[::-1]  # (T-window, n)
        m_per_bar = signal_raw / K if abs(K) > 1e-12 else signal_raw
        out[window:] = np.exp(252.0 * m_per_bar) - 1.0
    out[:window] = np.nan
    return out


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta fractional-difference trend score for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    lookbacks = param_lists["lookback"]
    ds = param_lists["frac_d"]

    log_close = np.log(close.to_numpy().astype(np.float64))
    result = np.full((T, n_candidates * n_symbols), np.nan)

    for lb, d in {(int(lookbacks[i]), float(ds[i])) for i in range(n_candidates)}:
        candidate_indices = [
            i for i in range(n_candidates) if int(lookbacks[i]) == lb and float(ds[i]) == d
        ]
        arr = _score_fracdiff(log_close, int(lb), float(d))
        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"trend_score": result}
