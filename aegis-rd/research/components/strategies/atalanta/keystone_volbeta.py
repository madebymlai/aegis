# %% component overview
# Atalanta KEYSTONE + VOL-SCALING EXPONENT (atalanta.keystone_volbeta) - the champion
# keystone_shortmute with ONE generalization: the inverse-vol divisor becomes vol**vol_beta.
# vol_beta = 1.0 is full inverse-vol sizing -> reproduces the champion bit-for-bit (nested control).
# vol_beta = 0.0 is magnitude-only (vol-blind) sizing; interior values partially de-emphasize vol.
#
# WHY: Kaminski-Hoffman "The Taming of the Skew" - inverse-vol / constant-risk sizing has the LOWEST
# skew because it cuts a leg's weight exactly as that leg's vol spikes (i.e. as the crisis leg pays).
# Lowering the exponent weights the high-vol (crisis-paying) legs MORE, the hypothesized convexity
# lift ([[notes/trend-speed-buys-drawdown-not-convexity]] follow-up; the sizing axis).
#
# HONEST STRUCTURAL NOTE: because vol appears in BOTH the leg numerator AND the gross divisor
# (FORGO gross from the uncapped signed book), vol_beta mainly re-weights the CROSS-SECTIONAL split
# among the three legs - it is NOT the full time-series "let gross rise in stress" ERT mechanism
# (that is gross-normalized away here, and would be the tail sleeve's equity-linked job anyway).
# short_cap is applied to the raw score reading BEFORE the vol divisor, exactly as the champion.
#
# Live-research parity: latch, shortable gate, one-sided cap and vol exponent are all causal
# functions of the score/vol history and the (static) borrow set; the live path recomputes identical.

# %% imports
import numpy as np
import pandas as pd

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.keystone_volbeta",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["enter_band", "exit_band", "short_cap", "vol_beta"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"enter_band": 0.10, "exit_band": 0.05, "short_cap": 1.0, "vol_beta": 1.0},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01

# The deliberate SHORT whitelist: the inflation-crisis short-bond leg only (matches keystone).
_BORROWABLE = frozenset({"IDTL", "TLT", "SPTL", "EDV"})


# %% parameter space
def param_space():
    """Champion bands / short_cap pinned by the config; the vol-scaling exponent is the swept lever.

    ``vol_beta`` 1.0 is full inverse-vol (the champion control); 0.0 is magnitude-only (vol-blind);
    interior values locate any convexity peak from de-emphasizing the high-vol crisis legs.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "enter_band": vbt.Param([0.10]),
        "exit_band": vbt.Param([0.05]),
        "short_cap": vbt.Param([0.10]),
        "vol_beta": vbt.Param([0.0, 0.25, 0.50, 0.75, 1.0]),
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
    """Schmitt-trigger sign latch per symbol: +1 up, -1 down, prior state held in the dead-zone."""

    signal = np.where(score_2d > enter_band, 1.0, np.where(score_2d < -exit_band, -1.0, np.nan))
    state = pd.DataFrame(signal).ffill().to_numpy()
    return np.where(np.isfinite(state), state, 0.0)


def _candidate_weights(score_2d, vol_2d, enter_band, exit_band, short_cap, vol_beta, shortable_row):
    """Champion FORGO weights with the inverse-vol divisor generalized to vol**vol_beta.

    Identical to keystone_shortmute at vol_beta = 1.0: hysteretic sign, continuous magnitude scaled
    by 1/vol**beta, gross from the UNCAPPED signed book, one-sided short-reading cap, freed gross to
    cash. Only the vol exponent moves.
    """

    vol = np.maximum(vol_2d, _MIN_VOL) ** vol_beta
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
    """Vectorized hysteretic L/S FORGO straddle with a swept vol-scaling exponent."""

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
    vol_betas = param_lists["vol_beta"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :],
            float(enter_bands[ci]), float(exit_bands[ci]),
            float(short_caps[ci]), float(vol_betas[ci]), shortable_row,
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
