# %% component overview
# Atalanta CROSS-SECTIONAL MOMENTUM (atalanta.cross_sectional_momentum) - a dollar-neutral,
# relative-strength leg that ranks a homogeneous cross-section ACROSS symbols each bar and goes
# long the strongest / short the weakest. It is the deliberate opposite of the keystone champion,
# which sizes each symbol on its OWN time-series trend: here a symbol's weight comes only from its
# RANK against its peers, so the leg carries ~zero net exposure to the shared (equity) factor and
# pays on cross-market DISPERSION, not direction.
#
# WHY (issue #80, trend-Q1 hyp #2, [[where-convexity-still-lives]]): the convex non-trend complement.
# Roncalli/Jusselin - time-series momentum likes zero-correlated assets (the champion's rates/gold/
# commodity legs), cross-sectional momentum likes CORRELATED, homogeneous ones (country equity
# indices, which all move together). Country equities are useless in the time-series engine (they
# just stack equity beta from the DECAYED corner) and are exactly right here: dollar-neutral -> ~0
# net equity beta, convex via dispersion, near-orthogonal to the trend book. Versor's GET is the
# live instance; their result is that COMBINING a convex non-trend leg with trend beats pure trend
# on both return and convexity.
#
# CONSTRUCTION: each bar, rank the cross-section by trend_score; take the top `n_side` long and the
# bottom `n_side` short, inverse-vol weighted WITHIN each side, then normalize each side to a 0.5
# gross so the book is gross 1 / net 0 (exact dollar-neutral). Fewer names (small n_side) is the
# FEE lever - on a EUR 5k book with a EUR 1.25/order floor, holding 2L/2S = 4 positions rather than
# the whole basket is what keeps the fill count survivable (the destsweep fee-floor lesson). Warmup
# or too-few-valid-names rows go flat.
#
# CAVEAT (pre-registered): the SHORT side borrows single-country equity ETFs; borrow availability on
# a small retail account is not modelled (the sim charges only the flat short_borrow_rate carry).
# And a hard top/bottom-k cutoff flips names on rank shuffles - the portfolio drift band is the only
# turnover damper, so the fill count is the first kill axis to read.

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.cross_sectional_momentum",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["n_side"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"n_side": 2},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """Sweep ``n_side`` - the number of names held long AND short each bar.

    ``n_side`` is the fee lever: 2 holds 4 positions (2L/2S), 3 holds 6. Smaller is coarser but
    cheaper on the per-order fee floor; larger captures more of the cross-section's dispersion at
    more fills. The trend_score lookback (the rank horizon) is swept via the indicator config across
    63/126/252 for the v28 spec-luck guard - this space stays on the construction lever.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {"n_side": vbt.Param([2])}


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators'."""
    return 0


# %% helpers
def _cs_weights(score_2d, vol_2d, n_side):
    """Dollar-neutral long-top / short-bottom inverse-vol weights from a cross-sectional rank.

    Per bar: rank the finite scores, take the top ``n_side`` long and bottom ``n_side`` short,
    inverse-vol weight within each side, and normalize each side to 0.5 gross (book gross 1, net 0).
    A bar with fewer than ``2 * n_side`` finite scores (warmup, or a short history) goes flat.
    """

    T, N = score_2d.shape
    weights = np.zeros((T, N))
    inv_vol = 1.0 / np.maximum(vol_2d, _MIN_VOL)
    for t in range(T):
        scores = score_2d[t]
        valid = np.where(np.isfinite(scores))[0]
        if valid.size < 2 * n_side:
            continue
        order = valid[np.argsort(scores[valid])]  # ascending: weakest first
        shorts, longs = order[:n_side], order[-n_side:]
        long_w = inv_vol[t, longs]
        short_w = inv_vol[t, shorts]
        weights[t, longs] = 0.5 * long_w / long_w.sum()
        weights[t, shorts] = -0.5 * short_w / short_w.sum()
    return weights


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized dollar-neutral cross-sectional momentum across the tradeable universe."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    n_sides = param_lists["n_side"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _cs_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], int(n_sides[ci])
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
