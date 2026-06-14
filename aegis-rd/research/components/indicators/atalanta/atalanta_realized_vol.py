# %% component overview
# Atalanta realized volatility — annualized rolling std of daily log returns per
# symbol. Feeds the trend sleeve's inverse-vol sizing so each name contributes
# comparable risk (a 1%/day UUP move and a 3%/day XLE move are not the same bet).
# Computed on the full series so the rolling warmup is incurred once, not
# re-incurred per split window (the windowed-compute-in-indicator rule).

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.realized_vol",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["vol_window"],
    "output_names": ["realized_vol"],
    "defaults": {"vol_window": 63},
}


# %% parameter space
def param_space():
    """Return VBT-native realized-vol windows (monthly / quarterly)."""

    return {
        "vol_window": vbt.Param([21, 63]),
    }


# %% helpers
def _realized_vol(close, window):
    """Annualized rolling std of daily log returns: std_window(log Close ratio) * sqrt(252)."""

    log_ret = np.log(close / close.shift(1))
    vol = log_ret.rolling(window).std(ddof=1) * np.sqrt(252.0)
    return vol


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta realized vol for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    windows = param_lists["vol_window"]

    result = np.full((T, n_candidates * n_symbols), np.nan)
    for w in set(windows):
        candidate_indices = [i for i in range(n_candidates) if windows[i] == w]
        arr = _realized_vol(close, int(w)).values
        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"realized_vol": result}
