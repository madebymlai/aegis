# %% component overview
# Aegis trailing momentum — the tail ETP's own realized-carry state: trailing
# ``mom_window`` simple return of Close. In calm contango the long-VIX ETP grinds down
# (the roll bleed), so trailing momentum sits negative; in sustained stress it turns
# positive. This is the price-only proxy for the expected-carry throttle (H3 of
# monetizing-the-tail-sleeve): the canonical signal is the VIX/VIX3M term-structure state
# (Six Figure Investing 0.917 threshold, Barclays XVZ 0.9), but the corpus carries no
# implied-vol indices, and Cooper (NAAIM 2013) documents ETP momentum as the robust
# price-only alternative (MA-crossover rules failed his robustness tests; momentum did
# not). Deliberately SLOW lookbacks only: LVO's wrapper already runs the fast spike
# migration internally (VIX > 1.35x 15d MA), and the article forbids duplicating it.
# Computed full-series (windowed-compute-in-indicator rule).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "aegis.trail_momentum",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["mom_window"],
    "output_names": ["trail_momentum"],
    "defaults": {"mom_window": 63},
}


# %% parameter space
def param_space():
    """The robustness probe: monthly, quarterly, semi-annual carry-state horizons.

    Three lookbacks BY DESIGN (the v28 spec-luck lesson): a keep requires the effect at
    two of three, not a single tuned window (Cooper's 83d is documented as snooped).
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "mom_window": vbt.Param([21, 63, 126]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars: the trailing-return window length."""
    return int(params["mom_window"])


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Trailing mom_window simple return per symbol, for all candidates."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    windows = param_lists["mom_window"]

    result = np.full((T, n_candidates * n_symbols), np.nan)
    for w in set(windows):
        mom = (close / close.shift(int(w)) - 1.0).values
        for ci in [i for i in range(n_candidates) if windows[i] == w]:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = mom

    return {"trail_momentum": result}
