# %% component overview
# Atalanta HYSTERETIC trend straddle, LONG-ONLY (FORGO convention). Purpose-built for the
# low-turnover convex sleeve: it keeps the champion's magnitude-aware inverse-vol FORGO sizing
# (continuous trend strength -> convexity) but replaces the raw sign gate with a SCHMITT-TRIGGER
# state latch, so the sign flips only on a CONFIRMED reversal across a dead-zone, not on every
# noise crossing of zero. That sign stickiness is the turnover lever; the holding between trades
# is owned by the portfolio drift band (rebalance_band), so this strategy has NO per-bar buffer.
#
# This is the magnitude-preserving hybrid the A/B pointed to: the binary Donchian-state latch cut
# fills and drawdown but discarded trend MAGNITUDE and lost convexity (0.24 -> 0.11); the
# continuous regression slope held convexity but flipped sign on near-zero noise (more fills).
# Here the SIGN is hysteretic (Schmitt trigger, few flips) and the MAGNITUDE is the continuous
# inverse-vol slope (convexity kept) - the best part of each.
#
# State machine (per symbol, on the consumed trend_score):
#   LONG  (+1) once score > +enter_band ; DOWN (-1) once score < -exit_band ; hold prior in the
#   dead-zone [-exit_band, +enter_band]. Forward-filled; warmup / pre-first-signal reads as flat.
# Sizing (FORGO, cash-when-flat): a latched-up name is sized by max(score,0)/vol; a latched-down
# name carries its would-be-short budget into the SIGNED gross and is then dropped to CASH, so few
# uptrends de-risk the book toward cash (gross <= 1) - the validated tail invariant, unchanged.
#
# Live-research parity: the latch is a causal function of the score history (the live path
# recomputes the identical state and reads its latest row); there is no per-bar NaN-hold or
# execution-side gate. Still ABSOLUTE/time-series momentum and still de-risks in downtrends, so the
# lookback-straddle convexity is preserved ([[what-makes-a-trend-sleeve-convex]]).
# direction must be `longonly` (all weights >= 0).

# %% imports
import numpy as np
import pandas as pd
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.trendStraddleHystereticLongOnly",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["enter_band", "exit_band"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"enter_band": 0.05, "exit_band": 0.05},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (see trendStraddle).
_MIN_VOL = 0.01


# %% parameter space
def param_space():
    """Schmitt-trigger thresholds (annualized score units): entry dead-zone x exit dead-zone.

    The dead-zone width (enter_band + exit_band) is the hysteresis: wider holds the sign through
    deeper chop (fewer flips, more lag). enter_band 0 is eager-entry / sticky-exit (asymmetric).
    """

    return {
        "enter_band": vbt.Param([0.0, 0.05, 0.10]),
        "exit_band": vbt.Param([0.05, 0.10]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators'."""
    return 0


# %% helpers
def _hysteretic_state(score_2d, enter_band, exit_band):
    """Schmitt-trigger sign latch per symbol: +1 up, -1 down, prior state held in the dead-zone.

    +1 once score > +enter_band, -1 once score < -exit_band; otherwise carry the last state
    forward. The two thresholds are mutually exclusive (both bands >= 0). NaN (warmup) and the
    rows before the first breach read as flat (0): no state, no position.
    """

    signal = np.where(score_2d > enter_band, 1.0, np.where(score_2d < -exit_band, -1.0, np.nan))
    state = pd.DataFrame(signal).ffill().to_numpy()
    return np.where(np.isfinite(state), state, 0.0)


def _candidate_weights(score_2d, vol_2d, enter_band, exit_band):
    """Long-only, magnitude-aware, hysteretic FORGO weights (cash-when-flat).

    Sign is the latched Schmitt state (sticky); magnitude is the continuous inverse-vol trend
    strength (convex). The signed gross includes latched-down names' would-be-short budget, which
    is then clipped to CASH - so when few names trend up the book de-risks toward cash (gross <= 1),
    exactly the champion's FORGO tail invariant, but with a hysteretic (low-turnover) sign.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    state = _hysteretic_state(score_2d, enter_band, exit_band)

    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / vol  # latched-up: positive strength
    short_leg = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / vol  # latched-down: would-be short
    signed = long_leg - short_leg
    gross = np.abs(signed).sum(axis=1, keepdims=True)  # pre-clip signed gross (incl. would-be shorts)
    longs = np.maximum(signed, 0.0)  # long only: drop short legs; their budget becomes cash
    return longs / np.where(gross > 0.0, gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized hysteretic long-only absolute-momentum straddle for all candidates."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    enter_bands = param_lists["enter_band"]
    exit_bands = param_lists["exit_band"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], float(enter_bands[ci]), float(exit_bands[ci])
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
