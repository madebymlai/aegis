# %% component overview
# Atalanta KEYSTONE + INVERSE-ETF SHORT LEG (atalanta.keystone_inverseshort) - the champion keystone
# with ONE change to HOW the Treasury short is taken: instead of a borrow-gated NEGATIVE weight on
# the underlying (IDTL), the short is realized as a LONG weight on a paired -1x inverse Treasury ETF.
# The book is therefore LONG-ONLY (no borrow, portfolio.direction = long), and the daily-reset decay
# of the -1x ETF - which the price series already carries - lands on the FAVOURABLE side of a
# trend-gated hold ([[trend-following-under-a-fixed-per-order-fee]] short-leg section): the -1x decay
# coefficient is (b^2 - b)/2 = 1 unit of realized variance, small in a sustained down-trend (low
# noise vs the move) and only biting in chop, which the hysteretic latch excludes.
#
# GROSS PARITY (the load-bearing design): the FORGO gross is computed on the BASE book
# [IDTL, IGLN, ICOM] EXACTLY as the champion does (unclipped signed book incl. the would-be IDTL
# short), so the long legs and the cash-when-flat divisor are byte-identical to the long-only
# champion. IDTL's down-conviction magnitude (max(-score,0)/vol) is then routed to a POSITIVE weight
# on the inverse ETF, filling the reserved short budget with an inverse LONG instead of cash. The
# inverse ETF's OWN score/vol are ignored (it carries no independent trend leg and does NOT enter the
# gross divisor) - so the Treasury-down axis is counted ONCE. Net effect vs the champion: the IDTL
# SHORT (negative weight on IDTL) is replaced by an equal-magnitude LONG weight on the inverse ETF;
# every long leg is unchanged. That isolates exactly one variable - the short's INSTRUMENT.
#
# inv_cap is the one-sided cap on the routed short magnitude (annualized-score units, identical
# semantics to keystone_shortmute.short_cap): 1.0 never binds (reproduces the uncapped short via the
# inverse ETF); 0.10 matches the live champion's cap for an instrument-only A/B. The hypothesis is
# that the cleaner instrument lets the cap be LOOSENED (inv_cap large) without the whipsaw-blowup the
# borrow-gated short suffered - recovering the 2022 crisis capture short_cap gives up.
#
# Live-research parity: the latch, the routed-short magnitude and the inverse pairing are causal
# functions of the BASE (IDTL) score history and the (static) pairing map; the live path recomputes
# the identical target and reads its latest row. Requires portfolio.direction = long. The inverse
# ETF's borrow/financing is inside its swap (priced by its own price series), not a portfolio short.

# %% imports
import numpy as np
import pandas as pd
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.keystone_inverseshort",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["enter_band", "exit_band", "inv_cap"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"enter_band": 0.10, "exit_band": 0.05, "inv_cap": 1.0},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01

# The inverse-ETF pairing: {inverse base symbol -> underlying base symbol whose SHORT it realizes}.
# E572 = Amundi/Lyxor US Treasury Bond Future Daily (-1x) Inverse UCITS ETF (15-25yr) realizes the
# IDTL (US Treasury 20+yr) short. The inverse leg is driven ENTIRELY by its base's down-conviction;
# its own trend score is never read.
_INVERSE_OF = {"E572": "IDTL"}


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


# %% parameter space
def param_space():
    """Champion bands pinned; the inverse-leg cap is the swept lever.

    ``inv_cap`` caps the routed short magnitude max(-score_base, 0) before inverse-vol sizing, in
    annualized-score units (identical semantics to keystone_shortmute.short_cap). 0.0 zeroes the
    inverse leg (pure long-only 3-name baseline == "drop the short"); 0.10 matches the live champion's
    short_cap so the pair isolates ONLY the short's instrument (borrow-gated IDTL short vs long -1x
    ETF); 1.0 never binds -> the uncapped short realized through the inverse ETF.
    """

    return {
        "enter_band": vbt.Param([0.10]),
        "exit_band": vbt.Param([0.05]),
        "inv_cap": vbt.Param([0.0, 0.10, 0.20, 1.0]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators'."""
    return 0


def _column_roles(columns):
    """Return (is_inverse, base_index) per column.

    ``is_inverse[j]`` is True when column j is a paired inverse ETF; ``base_index[j]`` is the column
    index of its underlying base (or -1). Base columns keep ``base_index = -1``.
    """

    symbols = [_base_symbol(c) for c in columns]
    sym_to_idx = {s: i for i, s in enumerate(symbols)}
    is_inverse = np.zeros(len(symbols), dtype=bool)
    base_index = np.full(len(symbols), -1, dtype=int)
    for j, sym in enumerate(symbols):
        base_sym = _INVERSE_OF.get(sym)
        if base_sym is not None and base_sym in sym_to_idx:
            is_inverse[j] = True
            base_index[j] = sym_to_idx[base_sym]
    return is_inverse, base_index


def _candidate_weights(score_2d, vol_2d, enter_band, exit_band, inv_cap, is_inverse, base_index):
    """Long-only FORGO weights with the Treasury short routed to a paired inverse-ETF LONG.

    Gross is the champion's unclipped signed book over the BASE columns only (byte-identical divisor,
    cash-when-flat preserved). Each base column contributes its long leg (its would-be short forgone);
    each inverse column contributes its base's capped down-conviction as a POSITIVE weight. Inverse
    columns never read their own score and never enter the gross divisor.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    base_mask = ~is_inverse  # (n_symbols,)

    state = _hysteretic_state(score_2d, enter_band, exit_band)
    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / vol
    short_leg = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / vol

    # Gross from the BASE book only, unclipped signed (incl. would-be base shorts) - the champion divisor.
    signed_base = (long_leg - short_leg) * base_mask[np.newaxis, :]
    gross = np.abs(signed_base).sum(axis=1, keepdims=True)

    # Base columns: keep the long leg, forgo the short to cash (long-only, no borrow).
    kept = long_leg * base_mask[np.newaxis, :]

    # Inverse columns: fill the reserved short budget of the paired base with a capped LONG weight.
    capped_short = np.minimum(short_leg, inv_cap / vol)  # cap max(-score,0) at inv_cap, then /vol
    for j in np.flatnonzero(is_inverse):
        b = int(base_index[j])
        kept[:, j] = capped_short[:, b]

    return kept / np.where(gross > 0.0, gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized long-only hysteretic trend sleeve; the Treasury short is a paired inverse-ETF long."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    is_inverse, base_index = _column_roles(close.columns)

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    enter_bands = param_lists["enter_band"]
    exit_bands = param_lists["exit_band"]
    inv_caps = param_lists["inv_cap"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :],
            float(enter_bands[ci]), float(exit_bands[ci]), float(inv_caps[ci]),
            is_inverse, base_index,
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
