# %% component overview
# Atalanta trend score, EFFICIENCY-RATIO QUALITY-GATED regression variant - the champion's annualized
# OLS slope of log price, held at full proportional magnitude when the trend is CLEAN and set to FLAT
# (zero) when the trend is CHOP, judged by Kaufman's Efficiency Ratio over the same window:
#     ER = |logP_t - logP_{t-lb}| / sum_k |logP_{t-k} - logP_{t-k-1}|      (net travel / path length)
#     trend_score = score            if ER >= er_gate
#                 = 0                 otherwise
# A drop-in for atalanta.trend_score_regress (same output name and units), so keystone_shortmute
# consumes it unchanged. This is the ROBUST, unit-free realization of the "significance-aware" trend
# signal - the actual best-practice trend-quality measure, chosen over two inferior alternatives the
# design research ruled out: (1) the Baltas t-statistic of the slope, which for log-price-on-time is
# unit-root INFLATED (a near-random-walk posts a huge t, so a fixed cutoff never gates); (2) the
# R^2-weighted slope proxy tried on [[2026-07-07#atalanta_trend_meaningful]], which SHRANK the
# magnitude toward the enter/exit dead-zone and so CHURNED more, the opposite of abstention. The
# Efficiency Ratio (Kaufman) sidesteps both: it is bounded [0,1], scale-free, and measures signal-to-
# noise of price TRAVEL directly (ER ~ 1 a straight ramp, ER ~ 0 a drunkard's walk), so gating on it
# is the clean Baltas-style "stay flat in statistically-insignificant trends" (turnover down ~2/3 at
# equal pre-cost Sharpe) without the t-stat's inflation or the proxy's churn.
#
# CONVEXITY-PRESERVING BY CONSTRUCTION. When ER clears the gate the score is the champion's PROPORTIONAL
# magnitude, untouched (CFM: proportional, uncapped sizing is what carries convexity; sign / capping /
# smoothing destroy it). The gate only ZEROES the chop periods - it never rescales the surviving trend -
# so the convex right tail the sleeve is hired for is left intact and only the whipsaw-bleed windows
# are dropped. Honest prior: an abstention gate is the AQR "can't filter your way out of whipsaw"
# family already killed here three ways ([[2026-06-29]] fast modulator gate; the R^2 proxy; by
# extension the Baltas gate) - it forfeits convex capture on false-positive pullbacks about as often as
# it saves a true reversal on this thin 3-leg book. This build gives that mechanism its BEST shot: the
# robust ER measure and the co-swept speed (a quality gate may unlock the fast band the raw slope could
# not afford - the lookback is unlocked over {21..252}, not pinned).
#
# NESTING. At er_gate = 0.0, ER >= 0 always, so the gate never fires and trend_score reduces to the
# champion slope byte-for-byte (the code short-circuits the ER arm at er_gate = 0, so the nested
# control is exact). Computed on the full series so the window warmup is incurred once (the windowed-
# compute-in-indicator rule); a strictly CAUSAL trailing window (live-research parity).

# %% imports
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.trend_score_erquality",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["lookback", "er_gate"],
    "output_names": ["trend_score"],
    "defaults": {"lookback": 189, "er_gate": 0.0},
}


# %% parameter space
def param_space():
    """Co-sweep trend SPEED and the Efficiency-Ratio gate threshold.

    ``lookback`` spans the FULL speed range {21, 42, 63, 126, 189, 252} - unlocked on purpose: the raw
    slope's convexity peaks at 189 ([[2026-06-29]] speedsweep), but a quality gate changes the turnover
    economics, so the fast band that whipsawed naked may become viable once its chop is gated out. Let
    VBT co-optimize. ``er_gate`` spans champion (0.0, no gate) -> Kaufman's trend thresholds
    (0.2 / 0.3 / 0.4, "trend present" starting ~0.3).
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "lookback": vbt.Param([21, 42, 63, 126, 189, 252]),
        "er_gate": vbt.Param([0.0, 0.2, 0.3, 0.4]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars for the gated score: the slope / ER window length."""
    return int(params["lookback"])


# %% helpers
def _score_slope(log_close, window):
    """Champion annualized OLS slope exp(slope*252)-1 over ``window``, byte-identical to
    atalanta.trend_score_regress (fixed linear filter, one sliding dot product)."""

    T, n_symbols = log_close.shape
    out = np.full((T, n_symbols), np.nan)
    if T >= window and window >= 2:
        x = np.arange(window, dtype=np.float64)
        x_centered = x - x.mean()
        weights = x_centered / (x_centered @ x_centered)
        windows = sliding_window_view(log_close, window, axis=0)  # (M, n_symbols, window)
        out[window - 1 :] = np.exp((windows @ weights) * 252.0) - 1.0
    out[:window] = np.nan
    return out


def _efficiency_ratio(log_close, window):
    """Kaufman Efficiency Ratio per column over ``window``: |net move| / path length, in [0, 1].

    net_t = |logP_t - logP_{t-window}| ; path_t = sum of the window's |daily log moves|. A flat window
    (path 0) is maximal chop -> ER 0.
    """

    T, n_symbols = log_close.shape
    er = np.full((T, n_symbols), np.nan)
    if T > window and window >= 1:
        abs_ret = np.abs(np.diff(log_close, axis=0))  # (T-1, n); abs_ret[j] = |logP[j+1]-logP[j]|
        csum_pad = np.vstack([np.zeros((1, n_symbols)), np.cumsum(abs_ret, axis=0)])  # (T, n)
        idx = np.arange(window, T)
        path = csum_pad[idx] - csum_pad[idx - window]  # sum of the window's |daily log moves|
        net = np.abs(log_close[idx] - log_close[idx - window])
        er[idx] = np.where(path > 0.0, net / path, 0.0)
    er[:window] = np.nan
    return er


def _score_gated(log_close, window, er_gate):
    """Champion slope score, zeroed on the bars where the Efficiency Ratio fails the gate."""

    score = _score_slope(log_close, window)
    if er_gate <= 0.0:
        return score  # nested champion: gate never fires, byte-exact
    er = _efficiency_ratio(log_close, window)
    return np.where(er >= er_gate, score, 0.0)


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta Efficiency-Ratio-gated trend score for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    lookbacks = param_lists["lookback"]
    gates = param_lists["er_gate"]

    log_close = np.log(close.to_numpy().astype(np.float64))
    result = np.full((T, n_candidates * n_symbols), np.nan)

    for lb, g in {(int(lookbacks[i]), float(gates[i])) for i in range(n_candidates)}:
        candidate_indices = [
            i for i in range(n_candidates) if int(lookbacks[i]) == lb and float(gates[i]) == g
        ]
        arr = _score_gated(log_close, int(lb), float(g))
        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"trend_score": result}
