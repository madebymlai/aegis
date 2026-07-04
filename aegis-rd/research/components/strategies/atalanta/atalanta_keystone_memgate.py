# %% component overview
# Atalanta KEYSTONE + COMMODITY MEMORY GATE (atalanta.keystone_memgate) - the champion shortmute
# keystone with ONE addition: a continuous variance-ratio ramp that scales the COMMODITY legs'
# (IGLN/ICOM) trend magnitude by how much memory the series currently has. Each gated leg's weight is
# multiplied by mem = clip((VR - vr_lo)/(vr_hi - vr_lo), 0, 1) from atalanta.variance_ratio: full
# weight when VR >= vr_hi (positively autocorrelated -> the trend persists, trust it), scaled to CASH
# as VR falls to vr_lo (mean-reverting -> the move is likely to whipsaw, stand aside), linear between.
# The gross is taken from the champion (un-gated) book, so a muted commodity leg's freed gross drops
# to CASH (a de-risk, FORGO), and the bond short leg (IDTL) and long gross stay byte-identical to the
# champion. ``vr_hi <= vr_lo`` disables the ramp -> reproduces keystone_shortmute exactly (nested).
#
# WHY continuous, not a binary gate: [[is-the-trend-premium-decaying]] h54 / Mehlitz-Auer (2024)
# resurrect a decayed commodity-momentum signal by CONDITIONING it on a variance-ratio memory measure.
# Their design is a CROSS-SECTIONAL double-sort (rank many commodities by momentum, then by VR); this
# book holds two commodity names, so the faithful adaptation is a per-leg TIME-SERIES conditioner. The
# representation is a CONTINUOUS multiplier, not a switch: the regime literature is explicit that a
# binary gate maximizes whipsaw/turnover cost (you pay the full spread on every flip) while continuous
# sizing degrades gracefully through the ambiguous transitions - which is exactly the cost this
# fixed-per-order-fee book cannot afford. It is the same continuous-forecast conditioning Carver/AQR
# use (position ~ forecast x regime-multiplier x inverse-vol), and it matches how atalanta already
# sizes (continuous inverse-vol magnitude); the asymmetric drift band absorbs the small bar-to-bar VR
# drift so only a real regime shift trades. NB Carver's own caveat: signal-strength conditioning has a
# marginal base rate ("not worth the complexity" in his tests), so the keep bar is a real held-out win.
#
# The gate touches ONLY the commodity legs (h54 is specific to IGLN/ICOM); the borrow-gated IDTL short
# and the champion's one-sided short_cap are untouched. Live-research parity: VR, the latch, the
# shortable gate and the ramp are all causal functions of the score/price history and static sets, so
# the live path recomputes the identical target.

# %% imports
import numpy as np
import pandas as pd

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.keystone_memgate",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["enter_band", "exit_band", "short_cap", "vr_lo", "vr_hi"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol", "variance_ratio"],
    "defaults": {"enter_band": 0.10, "exit_band": 0.05, "short_cap": 0.10, "vr_lo": 0.70, "vr_hi": 1.00},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01

# The SHORT whitelist: the inflation-crisis short-bond leg only (identical to keystone_shortmute).
_BORROWABLE = frozenset({"IDTL", "TLT", "SPTL", "EDV"})

# The MEMORY-GATED whitelist: the COMMODITY legs the variance-ratio ramp conditions - gold and broad
# commodity. IGLN/ICOM are the live UCITS lines; GLD/IAU (gold) and DBC (broad commodity) are their
# long-history US analogs used for the stress test - the same economic legs, so the set covers all.
_MEMORY_GATED = frozenset({"IGLN", "ICOM", "GLD", "IAU", "DBC"})


# %% parameter space
def param_space():
    """Champion pinned; the variance-ratio ramp knots are the swept lever.

    ``vr_hi`` is the "fully trust the trend" knot, pinned at the estimator's measured random-walk
    neutral (~1.0 for the pinned k21/W252). ``vr_lo`` is the "fully mute to cash" knot, swept over the
    mean-reverting tail the commodity legs actually visit (real-data VR(21,252) sits ~0.7-1.0 with a
    tail below ~0.8). ``vr_lo`` large (2.0) makes ``vr_hi <= vr_lo`` -> ramp OFF -> reproduces the
    champion exactly (the nested control). So this is a strict nested test of the memory gate.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "enter_band": vbt.Param([0.10]),
        "exit_band": vbt.Param([0.05]),
        "short_cap": vbt.Param([0.10]),
        "vr_lo": vbt.Param([2.00, 0.60, 0.70, 0.80]),  # 2.00 = ramp off (champion control)
        "vr_hi": vbt.Param([1.00]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators'."""
    return 0


# %% helpers
def _base_symbol(col):
    """Strip venue/currency suffix: 'IGLN.LSEETF' -> 'IGLN'."""
    return str(col).upper().split(".")[0].strip()


def _hysteretic_state(score_2d, enter_band, exit_band):
    """Schmitt-trigger sign latch per symbol: +1 up, -1 down, prior state held in the dead-zone.

    Identical to keystone: +1 once score > +enter_band, -1 once score < -exit_band; otherwise carry
    the last state forward. NaN (warmup) and rows before the first breach read as flat (0).
    """

    signal = np.where(score_2d > enter_band, 1.0, np.where(score_2d < -exit_band, -1.0, np.nan))
    state = pd.DataFrame(signal).ffill().to_numpy()
    return np.where(np.isfinite(state), state, 0.0)


def _memory_weight(vr_2d, vr_lo, vr_hi, gated_row):
    """Continuous VR ramp in [0,1] for the memory-gated (commodity) legs; 1.0 elsewhere.

    ``mem = clip((VR - vr_lo)/(vr_hi - vr_lo), 0, 1)`` - 1 at/above vr_hi (trust the trend), 0 at/below
    vr_lo (mean-reverting -> mute to cash), linear between. ``vr_hi <= vr_lo`` disables the ramp (the
    nested champion control). Non-gated legs (the bond short) and warmup/undefined VR (NaN) read 1.0,
    so the gate never mutes a leg it has no memory reading for.
    """

    if vr_hi <= vr_lo:
        return np.ones_like(vr_2d)
    ramp = np.clip((vr_2d - vr_lo) / (vr_hi - vr_lo), 0.0, 1.0)
    mem = np.where(gated_row, ramp, 1.0)
    return np.where(np.isfinite(vr_2d), mem, 1.0)


def _candidate_weights(
    score_2d, vol_2d, vr_2d, enter_band, exit_band, short_cap, vr_lo, vr_hi, shortable_row, gated_row
):
    """Champion shortmute FORGO weights, with the commodity legs' magnitude scaled by the VR ramp.

    The bond short leg, the long gross and the gross divisor are the champion's (gross from the
    UNGATED signed book); only the commodity legs are scaled by ``mem`` in [0,1], and the freed gross
    becomes cash. ``vr_hi <= vr_lo`` reproduces keystone_shortmute exactly.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    state = _hysteretic_state(score_2d, enter_band, exit_band)

    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / vol
    short_full = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / vol
    gross = np.abs(long_leg - short_full).sum(axis=1, keepdims=True)  # champion (ungated) gross divisor

    short_muted = np.where(state < 0.0, np.minimum(np.maximum(-score, 0.0), short_cap), 0.0) / vol
    signed = long_leg - short_muted  # champion signed book (one-sided short_cap)

    mem = _memory_weight(vr_2d, vr_lo, vr_hi, gated_row)  # [0,1] on the commodity legs only
    signed = signed * mem  # mute a mean-reverting commodity leg's trend -> its freed gross goes to cash

    kept = np.where(signed >= 0.0, signed, np.where(shortable_row, signed, 0.0))
    return kept / np.where(gross > 0.0, gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized hysteretic L/S straddle (borrow-gated short, one-sided short cap) with a continuous
    variance-ratio memory ramp on the commodity legs."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    shortable_row = np.array([[_base_symbol(c) in _BORROWABLE for c in close.columns]], dtype=bool)
    gated_row = np.array([[_base_symbol(c) in _MEMORY_GATED for c in close.columns]], dtype=bool)

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    vr_3d = inputs.indicators["variance_ratio"].reshape(T, n_candidates, n_symbols)
    enter_bands = param_lists["enter_band"]
    exit_bands = param_lists["exit_band"]
    short_caps = param_lists["short_cap"]
    vr_los = param_lists["vr_lo"]
    vr_his = param_lists["vr_hi"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], vr_3d[:, ci, :],
            float(enter_bands[ci]), float(exit_bands[ci]), float(short_caps[ci]),
            float(vr_los[ci]), float(vr_his[ci]), shortable_row, gated_row,
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
