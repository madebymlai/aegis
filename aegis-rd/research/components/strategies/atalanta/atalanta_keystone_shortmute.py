# %% component overview
# Atalanta KEYSTONE + ONE-SIDED SHORT MUTE (atalanta.keystone_shortmute) - the champion keystone
# with ONE addition: a one-sided cap on the SHORT reading. The short leg's conviction
# (max(-score, 0)) is capped at `short_cap` before inverse-vol sizing, so the deepest IDTL-short
# signals are compressed toward cash while the LONG leg is left completely uncapped. The gross is
# taken from the UNCAPPED book, so the muted short's freed gross drops to CASH (a de-risk) and the
# long weights stay byte-identical to the champion.
#
# WHY one-sided: Invesco "Navigating Momentum Crashes" (Q2 2024) - muting only the most-negative
# readings (leaving the positive tail uncapped) cuts drawdown while preserving crisis gains, because
# the deepest whipsaw losses come from holding full inverse exposure into a sharp reversal. On this
# book the only short is the borrow-gated IDTL leg, so the mute targets exactly the short-bond
# whipsaw without touching the long gold/commodity legs. The asymmetry is deliberate: capping the
# long tail would trade away convexity; compressing the short extreme is drawdown control
# ([[trend-following-in-whipsaw-regimes]]). `short_cap` large (1.0) never binds -> reproduces the
# champion exactly, so the lever is a strict nested test.
#
# CAVEAT (pre-registered): the IDTL short's largest AND most profitable readings are the 2022
# inflation crisis (the drawdown-payer's purpose year), so muting the most-negative readings risks
# diluting that crisis capture - the keep/kill guards the 2022 split.
#
# Live-research parity: the latch, the shortable gate AND the one-sided cap are causal functions of
# the score history and the (static) borrow set; the live path recomputes the identical target.

# %% imports
import numpy as np
import pandas as pd
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.keystone_shortmute",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["enter_band", "exit_band", "short_cap"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"enter_band": 0.10, "exit_band": 0.05, "short_cap": 1.0},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01

# The deliberate SHORT whitelist: the inflation-crisis short-bond leg only. IDTL is the live UCITS
# line; TLT (iShares 20+yr, NASDAQ) and SPTL (SPDR Long-Term Treasury, NYSE Arca, 2007) are its
# long-history US analogs used for the stress test - the same economic leg (short long-duration
# Treasuries), so the whitelist covers all three.
_BORROWABLE = frozenset({"IDTL", "TLT", "SPTL", "EDV"})


# %% parameter space
def param_space():
    """Champion bands pinned; the one-sided short cap is the swept lever.

    ``short_cap`` is in annualized-score (return) units, applied to the short reading max(-score, 0).
    1.0 never binds (IDTL's slope magnitude stays well under 100%/yr) -> the champion control; 0.0
    mutes the short fully (IDTL long-only, forgoes to cash in downtrends); the interior values locate
    the convexity/drawdown peak (the 2026-06-29 first pass found 0.10 > 0.20, peak not yet bracketed).
    """

    return {
        "enter_band": vbt.Param([0.10]),
        "exit_band": vbt.Param([0.05]),
        "short_cap": vbt.Param([0.0, 0.10, 1.0]),
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


def _candidate_weights(score_2d, vol_2d, enter_band, exit_band, short_cap, shortable_row):
    """Champion hysteretic FORGO weights, with the short reading capped one-sided toward cash.

    The long leg and the gross divisor are the champion's (gross from the UNCAPPED signed book), so
    the long weights are unchanged; only the short reading is compressed at ``short_cap``, and the
    freed gross becomes cash. ``short_cap`` large reproduces keystone exactly.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    state = _hysteretic_state(score_2d, enter_band, exit_band)

    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / vol
    short_full = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / vol
    gross = np.abs(long_leg - short_full).sum(axis=1, keepdims=True)  # champion (uncapped) gross

    short_muted = np.where(state < 0.0, np.minimum(np.maximum(-score, 0.0), short_cap), 0.0) / vol
    signed = long_leg - short_muted
    kept = np.where(signed >= 0.0, signed, np.where(shortable_row, signed, 0.0))
    return kept / np.where(gross > 0.0, gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized hysteretic L/S straddle (borrow-gated short) with a one-sided short-reading cap."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    shortable_row = np.array(
        [[_base_symbol(c) in _BORROWABLE for c in close.columns]], dtype=bool
    )

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    enter_bands = param_lists["enter_band"]
    exit_bands = param_lists["exit_band"]
    short_caps = param_lists["short_cap"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :],
            float(enter_bands[ci]), float(exit_bands[ci]), float(short_caps[ci]), shortable_row,
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
