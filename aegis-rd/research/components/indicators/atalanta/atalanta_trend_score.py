# %% component overview
# Atalanta trend score — annualized time-series (absolute) momentum per symbol.
# Sign is the trend direction (uptrend long / downtrend de-risk), magnitude the
# trend strength; annualizing makes one threshold comparable across lookbacks.
# This is the long-gamma primitive of the floor's convex pole: absolute momentum
# (compare a symbol to its own past, threshold zero) de-risks in downtrends and so
# replicates a lookback straddle — the source of trend's positive crisis skew —
# unlike cross-sectional relative momentum, which stays invested in the least-bad
# asset through a crash. Lookbacks span the medium/long "workhorse" band (~3-12mo).

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.trend_score",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["lookback"],
    "output_names": ["trend_score"],
    "defaults": {"lookback": 126},
}


# %% parameter space
def param_space():
    """Return VBT-native lookback params over the medium/long trend band."""

    return {
        "lookback": vbt.Param([63, 126, 189, 252]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars for the trend score: the momentum lookback length."""
    return int(params["lookback"])


# %% helpers
def _trend_score(close, lookback):
    """Annualized absolute momentum: (Close(t) / Close(t - lookback))^(252/lookback) - 1.

    Computed on the full series so the lookback warmup is incurred once, not
    re-incurred per split window (the windowed-compute-in-indicator rule).
    """

    annualized = (close / close.shift(lookback)) ** (252 / lookback) - 1.0
    score = annualized.values.astype(np.float64)

    # Rows before the lookback are incomplete — NaN so the strategy's sign gate
    # correctly excludes warmup bars rather than reading a partial trend.
    score[:lookback] = np.nan

    return close.__class__(score, index=close.index, columns=close.columns)


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta trend score for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    lookbacks = param_lists["lookback"]

    result = np.full((T, n_candidates * n_symbols), np.nan)

    for lb in set(lookbacks):
        candidate_indices = [i for i in range(n_candidates) if lookbacks[i] == lb]
        arr = _trend_score(close, int(lb)).values
        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"trend_score": result}
