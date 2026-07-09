# %% component overview
# Atalanta HOLD-WRAPPER - the "BUY" arm of the trend-seat build-vs-buy test (GH #80, block 1,
# pre-registered as `dbmf_seatchallenger` in [[runs/atalanta/2026-07-09]]).
#
# A static LONG of a managed-futures UCITS wrapper proxy (WTMF / DBMF / KMLM). The fund runs the
# diversified trend logic INTERNALLY across ~10-15 futures markets, so owning it long IS owning the
# CTA's convex payoff - the breadth-in-a-box our EUR-5k UCITS book cannot assemble by hand. We apply
# NO trend signal of our own; the whole point is to buy the beta and judge it on the trend-seat
# scorecard (`trend_convexity_payoff` primary + standalone Sharpe) against the hand-built champion.
#
# The wrapper legs are inverse-vol weighted then gross-normalized to `gross_target`; for a SINGLE
# wrapper leg (the WTMF proxy the config uses) this collapses to a constant full-size long. The vol
# indicator is consumed only to keep the run on the proven indicator path and to blend multiple
# wrapper proxies coherently if more than one is listed; the wrapper is already internally
# vol-managed, so this is not a second vol-target layer.

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.hold_wrapper",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["gross_target"],
    "output_name": "target_weights",
    "consumes_outputs": ["realized_vol"],
    "defaults": {"gross_target": 1.0},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """A single static candidate: full-size long of the wrapper (gross_target = 1.0).

    Not swept - the challenger IS the buy-and-hold. A sub-1.0 gross_target (wrapper + cash) is a
    later dial, not this test.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {"gross_target": vbt.Param([1.0])}


# %% lookback
def lookback(**params):
    """No warmup beyond the vol indicator's own."""
    return 0


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Inverse-vol long of the wrapper leg(s), gross-normalized to gross_target (a constant
    full-size long for a single wrapper proxy)."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    gross_targets = param_lists["gross_target"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        vol = np.maximum(vol_3d[:, ci, :], _MIN_VOL)
        inv_vol = 1.0 / vol  # inverse-vol long; a single wrapper leg -> constant after gross-norm
        gross = inv_vol.sum(axis=1, keepdims=True)
        result_3d[:, ci, :] = np.where(gross > 0.0, inv_vol / gross, 0.0) * float(gross_targets[ci])

    return result_3d.reshape(T, n_candidates * n_symbols)
