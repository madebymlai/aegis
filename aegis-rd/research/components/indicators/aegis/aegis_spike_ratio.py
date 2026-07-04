# %% component overview
# Aegis spike ratio — the tail position's own realized P&L path as a signal: Close divided
# by its rolling ``ref_window`` low. This is the path-dependent trigger base for the
# profit-multiple harvest (H2 of monetizing-the-tail-sleeve): Bhansali's monetization
# multiples are defined on an option's premium paid; a rolling-futures ETP has no premium,
# so the trailing low is the cost-basis proxy the article flags. A ratio of 3.0 means the
# instrument marks 3x its cheapest print of the trailing window — the "3x monetization"
# state. Deliberately NO external level (VIX, term structure): a level trigger synchronizes
# with everyone else's identical rule; the position's own path does not (Volmageddon
# guardrail in the article). Computed full-series so the rolling warmup is incurred once
# (the windowed-compute-in-indicator rule).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "aegis.spike_ratio",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["ref_window"],
    "output_names": ["spike_ratio"],
    "defaults": {"ref_window": 63},
}


# %% parameter space
def param_space():
    """The trailing-low window: one quarter, the article's '60-day low' cost-basis proxy."""

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "ref_window": vbt.Param([63]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars: the rolling-min window length."""
    return int(params["ref_window"])


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Close over its rolling ref_window low, per symbol, for all candidates."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    windows = param_lists["ref_window"]

    result = np.full((T, n_candidates * n_symbols), np.nan)
    for w in set(windows):
        ratio = (close / close.rolling(int(w)).min()).values
        for ci in [i for i in range(n_candidates) if windows[i] == w]:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = ratio

    return {"spike_ratio": result}
