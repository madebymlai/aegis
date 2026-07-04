# %% component overview
# Atalanta KEYSTONE + TURNING-POINT GATE (atalanta.keystone_turngate) - the champion keystone
# (hysteretic-sign + continuous-magnitude FORGO core, borrow-gated IDTL short) with ONE addition: a
# fast trend read GATES the slow position. Where the fast slope (`trend_score_fast`) disagrees in
# sign with the slow hysteretic latch - a reversal the sticky slow latch is holding through - the
# name's weight is scaled toward `gate_strength` (0 = flat the name, 1 = no gate = the champion).
# The gate is applied AFTER the FORGO gross-normalization, so the freed gross goes to CASH (the
# intended de-risk), not redistributed to the other names.
#
# WHY a gate, not a fast leg: a fast TRADING leg buys its own whipsaw on a thin correlated book
# (killed 2026-06-10); the same fast signal used only as a turning-point MODULATOR on the slow
# position is a different instrument with published support - Harvey-Goulding-Mazzoleni "Breaking Bad
# Trends" (FAJ 2023): turning-point frequency drives weak trend and is not predictable ex ante, so
# react at the turn (fast/slow disagreement) rather than forecast. It targets exactly the reversal-
# sign losses the hysteresis and a trend-strength threshold both leave untouched
# ([[trend-following-in-whipsaw-regimes]]). `gate_strength = 1.0` reproduces the champion exactly,
# so the lever is a strict nested test.
#
# Live-research parity: the latch, the shortable gate AND the turn gate are causal functions of the
# slow/fast score history and the (static) borrow set; the live path recomputes the identical target
# and reads its latest row. Requires portfolio.direction = both.

# %% imports
import numpy as np
import pandas as pd

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.keystone_turngate",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["enter_band", "exit_band", "gate_strength"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "trend_score_fast", "realized_vol"],
    "defaults": {"enter_band": 0.10, "exit_band": 0.05, "gate_strength": 1.0},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01

# The deliberate SHORT whitelist: the inflation-crisis short-bond leg only (matches keystone).
_BORROWABLE = frozenset({"IDTL"})


# %% parameter space
def param_space():
    """Champion bands pinned; the turn-gate strength is the swept lever.

    enter_band / exit_band are fixed at the promoted champion so the only thing that moves is the
    gate. ``gate_strength`` 1.0 is the champion (no gate), 0.5 halves a name on a turn, 0.0 flats it.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "enter_band": vbt.Param([0.10]),
        "exit_band": vbt.Param([0.05]),
        "gate_strength": vbt.Param([0.0, 0.5, 1.0]),
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


def _turn_gate(state, fast_2d, gate_strength):
    """Per-name multiplier in {gate_strength, 1.0}: 1.0 where the fast slope agrees with the latch.

    Agreement (no gate) holds when the latch is flat, when the fast slope confirms the latch
    direction, or when the fast read is warmup-NaN. Disagreement (latched up but fast slope negative,
    or latched down but fast slope positive) is the turning point, and the name is scaled toward
    ``gate_strength``. ``gate_strength >= 1`` short-circuits to the champion (no gate).
    """

    if gate_strength >= 1.0:
        return 1.0
    fast_finite = np.isfinite(fast_2d)
    agree = (
        (~fast_finite)
        | (state == 0.0)
        | ((state > 0.0) & (fast_2d >= 0.0))
        | ((state < 0.0) & (fast_2d <= 0.0))
    )
    return np.where(agree, 1.0, gate_strength)


def _candidate_weights(score_2d, fast_2d, vol_2d, enter_band, exit_band, gate_strength, shortable_row):
    """Champion hysteretic FORGO weights, then a turning-point gate toward cash.

    The pre-gate block is identical to keystone (gross from the unclipped signed book, borrow-gated
    short side, divide by gross so gross <= 1). The gate then scales gated names toward
    ``gate_strength``; because it is applied after normalization, the freed gross drops to cash.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    state = _hysteretic_state(score_2d, enter_band, exit_band)

    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / vol
    short_leg = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / vol
    signed = long_leg - short_leg
    gross = np.abs(signed).sum(axis=1, keepdims=True)

    kept = np.where(signed >= 0.0, signed, np.where(shortable_row, signed, 0.0))
    weights = kept / np.where(gross > 0.0, gross, 1.0)
    return weights * _turn_gate(state, fast_2d, gate_strength)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized hysteretic L/S straddle (borrow-gated short) with a fast turning-point gate."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    shortable_row = np.array(
        [[_base_symbol(c) in _BORROWABLE for c in close.columns]], dtype=bool
    )

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    fast_3d = inputs.indicators["trend_score_fast"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    enter_bands = param_lists["enter_band"]
    exit_bands = param_lists["exit_band"]
    gate_strengths = param_lists["gate_strength"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], fast_3d[:, ci, :], vol_3d[:, ci, :],
            float(enter_bands[ci]), float(exit_bands[ci]), float(gate_strengths[ci]), shortable_row,
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
