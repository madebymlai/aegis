# %% component overview
# Atalanta KEYSTONE + EXTENSION-DRIVEN PYRAMIDING (atalanta.keystone_pyramid) - the champion shortmute
# keystone with ONE addition: each trend leg's magnitude ramps from a small entry tranche to full size
# as the OPEN TRADE EXTENDS in its own direction (measured in vol-normalized units since the latch
# entry). Exposure is therefore SMALLEST on fresh/young trends and largest exactly when a move has
# already run - the convex, right-tail-manufacturing shape. Freed gross drops to CASH (FORGO, gross<=1);
# the bond short and long gross stay byte-identical to the champion at full ramp. ``pyr_r <= 0`` disables
# the ramp -> reproduces keystone_shortmute EXACTLY (nested control).
#
# WHY EXTENSION-DRIVEN, not time-in-trend: the pyramiding literature is unanimous that the driver is how
# far the trade has PROFITED, not how many bars it is old. Mulvaney's disclosed multiplier is
# ``m = min(cap, 1 + floor(max(0, r) / K))`` with ``r = open-trade profit / initial risk`` (Concretum's
# reverse-engineering of his ~+5.98 trade-skew, 25-yr program); Concretum's Volatility-Parity+Pyramiding
# adds a full layer "each time price moves favorably by a 2x risk increment", capped at 4x, and shows it
# has the highest Profit Factor (1.74 vs 1.55 vs 1.48) precisely by "amplifying exposure to the right
# tail". CFM gives the theory: "if one continues to build up a position as trends get bigger, one assumes
# more risk infrequently - the definition of fat tails", i.e. building INTO an extended trend IS how the
# convex right tail is manufactured; capping early (what most managers do) sells it back. Our own prior
# atalanta pyramid (archived trendStraddleBufferedPyramid) used a TIME-in-trend ramp and flagged it a
# proxy; this rebuilds it on the SOTA extension driver. See [[what-makes-a-trend-sleeve-convex]] (the
# pyramiding hypothesis is SUPPORTED there - held-out skew +0.54->+0.65 AND Sharpe up on the sibling
# 20-name book, open question: does it help the live 3-name champion) and [[when-conditioning-pays]].
#
# WHY IT FITS THIS BOOK: inverse-vol sizing already acts as a TAKE-PROFIT - Quantica show vol rises ~1.2x
# into winning trends so constant-risk sizing cuts the top-quartile winners' notional by ~30%, i.e. the
# champion structurally UNDER-participates in accelerating trends. Extension-driven pyramiding is the
# exact corrective: it re-adds exposure on the moves that have run. The gross-cap-1 constraint (EUR 5k
# UCITS, no leverage) inverts the usual "decreasing-adds / never-inverted-pyramid" leverage-safety rule
# (which guards against over-levering the top tranche - impossible here since gross<=1): for a convexity-
# ranked book the correct shape is to START small on fresh trends and BUILD to full as they extend, which
# is what the ramp does, freeing gross to cash rather than re-levering survivors.
#
# The ramp touches every trend leg symmetrically (long or borrow-gated short), driven by that leg's own
# favorable extension since its latch entry; the one-sided short_cap and the borrow gate are untouched.
# Live-research parity: the latch, the entry anchor, the extension and the ramp are all causal functions
# of the score/price history and static sets, so the live path recomputes the identical target.

# %% imports
import numpy as np
import pandas as pd
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.keystone_pyramid",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["enter_band", "exit_band", "short_cap", "pyr_r", "pyr_floor"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"enter_band": 0.10, "exit_band": 0.05, "short_cap": 0.10, "pyr_r": 0.0, "pyr_floor": 0.0},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01

# The SHORT whitelist: the inflation-crisis short-bond leg only (identical to keystone_shortmute).
_BORROWABLE = frozenset({"IDTL", "TLT", "SPTL", "EDV"})


# %% parameter space
def param_space():
    """Champion pinned; the extension-to-full ramp threshold ``pyr_r`` is the swept lever.

    ``pyr_r`` is the vol-normalized favorable extension since the latch entry at which a leg reaches full
    weight: ``r = (cumulative favorable log-move since entry) / annualized_vol``, so ``pyr_r`` is measured
    in "years-equivalent of vol". ``pyr_r = 0`` disables the ramp -> reproduces keystone_shortmute exactly
    (the nested champion control). Active values bracket "builds to full in ~a month's move" (0.25) through
    "only the largest trends reach full" (1.0). ``pyr_floor`` (the fresh-entry tranche) is pinned at 0.0:
    a brand-new trend sits in cash and builds as it extends - the convexity-max shape for a gross<=1 book.
    """

    return {
        "enter_band": vbt.Param([0.10]),
        "exit_band": vbt.Param([0.05]),
        "short_cap": vbt.Param([0.10]),
        "pyr_r": vbt.Param([0.0, 0.25, 0.50, 1.00]),  # 0.0 = ramp off (champion control)
        "pyr_floor": vbt.Param([0.0]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators'."""
    return 0


# %% helpers
def _base_symbol(col):
    """Strip venue/currency suffix: 'IDTL.LSEETF' -> 'IDTL'."""
    return str(col).upper().split(".")[0].strip()


def _hysteretic_state(score_2d, enter_band, exit_band):
    """Schmitt-trigger sign latch per symbol: +1 up, -1 down, prior state held in the dead-zone.

    Identical to keystone: +1 once score > +enter_band, -1 once score < -exit_band; otherwise carry
    the last state forward. NaN (warmup) and rows before the first breach read as flat (0).
    """

    signal = np.where(score_2d > enter_band, 1.0, np.where(score_2d < -exit_band, -1.0, np.nan))
    state = pd.DataFrame(signal).ffill().to_numpy()
    return np.where(np.isfinite(state), state, 0.0)


def _pyramid_ramp(state_2d, logclose_2d, vol_2d, pyr_r, pyr_floor):
    """Per-name [pyr_floor, 1] multiplier ramping in with the leg's vol-normalized favorable EXTENSION.

    A "leg" is a maximal run of constant latched state; its entry anchor is the log price at the bar the
    state took its current non-flat value (reset on a sign flip). The favorable extension since entry is
    ``ext = state * (logP - logP_anchor)`` (>=0 when the trade is in profit), and its vol-normalized form
    ``r = max(ext, 0) / annualized_vol`` drives ``ramp = pyr_floor + (1 - pyr_floor) * clip(r / pyr_r, 0, 1)``:
    ``pyr_floor`` on a fresh trade, 1.0 once the move has extended ``pyr_r`` vol-units. ``pyr_r <= 0``
    disables the ramp (returns all ones, the nested champion). Flat bars read 1.0 (the leg is 0 anyway).
    """

    if pyr_r <= 0.0:
        return np.ones_like(logclose_2d)

    T, n = logclose_2d.shape
    vol = np.maximum(vol_2d, _MIN_VOL)
    ramp = np.ones((T, n))
    anchor = logclose_2d[0].copy()
    prev = np.zeros(n)
    for t in range(T):
        s = state_2d[t]
        new_leg = (s != 0.0) & (s != prev)  # a new non-flat leg began this bar -> reset the entry anchor
        anchor = np.where(new_leg, logclose_2d[t], anchor)
        ext = np.where(s != 0.0, s * (logclose_2d[t] - anchor), 0.0)  # favorable move since entry
        r = np.maximum(ext, 0.0) / vol[t]  # vol-normalized extension (years-equivalent of vol), >= 0
        p = pyr_floor + (1.0 - pyr_floor) * np.clip(r / pyr_r, 0.0, 1.0)
        ramp[t] = np.where(s != 0.0, p, 1.0)
        prev = s
    return ramp


def _candidate_weights(
    score_2d, vol_2d, logclose_2d, enter_band, exit_band, short_cap, pyr_r, pyr_floor, shortable_row
):
    """Champion shortmute FORGO weights, with each trend leg's magnitude scaled by its extension ramp.

    The gross divisor is the champion's (from the UNCAPPED, FULL-SIZE signed book), so a young or
    un-extended leg's held-back weight becomes CASH rather than re-levering the others; the bond short
    and long gross are the champion's at full ramp. ``pyr_r <= 0`` reproduces keystone_shortmute exactly.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    state = _hysteretic_state(score_2d, enter_band, exit_band)

    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / vol
    short_full = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / vol
    gross = np.abs(long_leg - short_full).sum(axis=1, keepdims=True)  # champion (ungated) gross divisor

    short_muted = np.where(state < 0.0, np.minimum(np.maximum(-score, 0.0), short_cap), 0.0) / vol
    signed = long_leg - short_muted  # champion signed book (one-sided short_cap)

    ramp = _pyramid_ramp(state, logclose_2d, vol_2d, pyr_r, pyr_floor)  # [pyr_floor, 1] per leg
    signed = signed * ramp  # hold back a young/un-extended leg's magnitude -> its freed gross goes to cash

    kept = np.where(signed >= 0.0, signed, np.where(shortable_row, signed, 0.0))
    return kept / np.where(gross > 0.0, gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized hysteretic L/S straddle (borrow-gated short, one-sided short cap) with an extension-
    driven pyramiding ramp on every trend leg."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    shortable_row = np.array([[_base_symbol(c) in _BORROWABLE for c in close.columns]], dtype=bool)
    logclose = np.log(close.to_numpy().astype(np.float64))

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    enter_bands = param_lists["enter_band"]
    exit_bands = param_lists["exit_band"]
    short_caps = param_lists["short_cap"]
    pyr_rs = param_lists["pyr_r"]
    pyr_floors = param_lists["pyr_floor"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], logclose,
            float(enter_bands[ci]), float(exit_bands[ci]), float(short_caps[ci]),
            float(pyr_rs[ci]), float(pyr_floors[ci]), shortable_row,
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
