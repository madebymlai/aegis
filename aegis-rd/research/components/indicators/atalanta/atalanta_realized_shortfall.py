# %% component overview
# Atalanta realized Expected Shortfall (CVaR) - annualized rolling mean of the worst
# `shortfall_alpha`-fraction of daily log returns per symbol. It is the tail-risk analog of
# atalanta.realized_vol: where realized_vol measures a symbol's *volatility*, this measures its
# *left-tail* magnitude, so a strategy can size by inverse-ES (tail-risk parity) instead of
# inverse-vol - down-weighting fat-left-tail legs relative to the Gaussian-implied inverse-vol
# weight ([[budgeting-the-divergent-seat]]; AllianceBernstein "An Introduction to Tail Risk Parity";
# Boudt et al. 2013 CVaR risk budgeting). For a Gaussian leg ES is just vol x a constant, so the two
# sizings differ ONLY by each leg's downside NON-normality - exactly the difference the tail-parity
# hypothesis is about. A moderate alpha (0.10-0.20) keeps the estimate data-efficient (the worst ~10-
# 20% of a rolling window, not a rare 1% exceedance whose finite-sample properties are poor).
#
# Annualized by sqrt(252) to sit on the same scale as realized_vol, so a geometric blend
# vol^(1-t) * ES^t is a smooth interpolation between inverse-vol and inverse-ES sizing (the common
# ES/vol scale cancels under gross-normalization; only the per-leg tail-fatness ratio drives the
# tilt). Computed on the full series so the rolling warmup is incurred once (the windowed-compute-in-
# indicator rule), and it is a strictly CAUSAL trailing window (live-research parity).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.realized_shortfall",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["shortfall_window", "shortfall_alpha"],
    "output_names": ["realized_shortfall"],
    "defaults": {"shortfall_window": 126, "shortfall_alpha": 0.10},
}


# %% parameter space
def param_space():
    """Return VBT-native ES windows/levels matched to the realized_vol windows.

    ``shortfall_window`` mirrors ``vol_window`` (a long window pairs with the long trend lookback);
    ``shortfall_alpha`` is the tail fraction averaged into the shortfall - 0.10 (worst decile) is the
    default data-efficient choice, 0.05/0.20 bracket it for the robustness guard.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "shortfall_window": vbt.Param([126]),
        "shortfall_alpha": vbt.Param([0.10]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars for realized ES: the rolling window length."""
    return int(params["shortfall_window"])


# %% helpers
def _expected_shortfall(returns_1d, window, alpha):
    """Annualized rolling Expected Shortfall of a single return series (raw numpy window).

    ES = -mean(r | r <= quantile_alpha(r)) over the trailing ``window``, x sqrt(252). Positive
    magnitude. The worst-alpha subset always contains at least the single worst observation, so the
    conditional mean is well defined for any non-empty window.
    """

    q = np.quantile(returns_1d, alpha)
    tail = returns_1d[returns_1d <= q]
    if tail.size == 0:  # degenerate (all-equal window); fall back to the minimum
        tail = returns_1d[returns_1d <= returns_1d.min()]
    return -tail.mean() * np.sqrt(252.0)


def _realized_shortfall(close, window, alpha):
    """Annualized rolling ES per column, from daily log returns."""

    import pandas as pd

    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).apply(
        lambda x: _expected_shortfall(x, window, alpha), raw=True
    )


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta realized Expected Shortfall for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    windows = param_lists["shortfall_window"]
    alphas = param_lists["shortfall_alpha"]

    result = np.full((T, n_candidates * n_symbols), np.nan)
    for w, a in {(int(windows[i]), float(alphas[i])) for i in range(n_candidates)}:
        candidate_indices = [
            i for i in range(n_candidates) if int(windows[i]) == w and float(alphas[i]) == a
        ]
        arr = _realized_shortfall(close, w, a).values
        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"realized_shortfall": result}
