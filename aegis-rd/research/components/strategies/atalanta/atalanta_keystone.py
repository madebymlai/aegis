# %% component overview
# Atalanta KEYSTONE (atalanta.keystone) - the definitive convex trend sleeve, the floor-tier
# long-gamma "drawdown payer". Hysteretic-sign + continuous-magnitude FORGO core (long-only,
# cash-when-flat), with ONE addition: a down-state name is actually SHORTED (negative weight)
# instead of forgone to cash IFF its base symbol is in the _BORROWABLE set; every other down-state
# name still drops to cash (long-only).
#
# WHY only IDTL: _BORROWABLE is the deliberate SHORT whitelist - the names we WANT to short, not
# everything that CAN be shorted. The thesis is one leg: short long-duration bonds (IDTL) in an
# inflation crisis, the quadrant the long-only book misses. Shorting every borrow-able name (gold
# etc.) was a net drag (it shorts a lone dipping safe-haven in a bull tape and gets run over on the
# rebound); narrowing the whitelist to the intended leg is the fix. IDTL is IBKR-borrowable
# (2026-06 probe), so the research short is realizable as the identical live short - parity-safe, no
# inverse-ETF proxy. To short an UN-borrowable axis, add an inverse UCITS ETF held long instead.
#
# Sizing (FORGO, gross from the UNCLIPPED signed book, reused as divisor so gross <= 1):
#   long_leg  = max(score,0)/vol on latched-UP names
#   short_leg = max(-score,0)/vol on latched-DOWN names
#   keep all longs + the shortable shorts; drop non-shortable shorts to CASH; divide by the full
#   pre-clip gross. The sign is the hysteretic Schmitt latch (sticky, low turnover); the magnitude
#   is the continuous inverse-vol trend strength (convex), on BOTH sides.
#
# Live-research parity: the latch and the shortable gate are causal functions of the score history
# and the (static) borrow set; the live path recomputes the identical target and reads its latest
# row. Requires portfolio.direction = both. Borrow carry on the short legs is priced by the
# portfolio (ADR-0008). Still absolute/time-series momentum; still de-risks longs in downtrends.

# %% imports
import numpy as np
import pandas as pd

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.keystone",
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

# The deliberate SHORT whitelist: the inflation-crisis short-bond leg only. IDTL (iShares $ Treasury
# 20+yr) is IBKR-borrowable (2026-06 paper probe, DUQ455398), so the research short is realizable as
# the identical live short - parity-safe. Every other down-state name (gold, broad commodity) stays
# long-only, forgone to cash.
_BORROWABLE = frozenset({"IDTL"})


# %% parameter space
def param_space():
    """Schmitt-trigger thresholds (annualized score units): entry dead-zone x exit dead-zone.

    Identical to the long-only variant; the dead-zone width (enter_band + exit_band) is the
    hysteresis. The short side uses the same latch, so a name is shorted only after a CONFIRMED
    downside breach, not on near-zero noise.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "enter_band": vbt.Param([0.0, 0.05, 0.10]),
        "exit_band": vbt.Param([0.05, 0.10]),
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

    +1 once score > +enter_band, -1 once score < -exit_band; otherwise carry the last state
    forward. NaN (warmup) and the rows before the first breach read as flat (0).
    """

    signal = np.where(score_2d > enter_band, 1.0, np.where(score_2d < -exit_band, -1.0, np.nan))
    state = pd.DataFrame(signal).ffill().to_numpy()
    return np.where(np.isfinite(state), state, 0.0)


def _candidate_weights(score_2d, vol_2d, enter_band, exit_band, shortable_row):
    """Hysteretic FORGO weights with a shortable-gated short side.

    ``shortable_row`` is a (1, n_symbols) bool mask of borrow-able names. Gross is taken from the
    UNCLIPPED signed book and reused as divisor (gross <= 1): longs keep baseline size, shortable
    shorts are kept (negative weight), non-shortable shorts drop to CASH. Sign = hysteretic latch;
    magnitude = continuous inverse-vol strength on both sides.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    state = _hysteretic_state(score_2d, enter_band, exit_band)

    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / vol  # latched-up: positive strength
    short_leg = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / vol  # latched-down: down strength
    signed = long_leg - short_leg
    gross = np.abs(signed).sum(axis=1, keepdims=True)  # unclipped signed gross (incl. all would-be shorts)

    # Keep every long; keep a short only where the name is borrow-able; drop the rest to cash.
    kept = np.where(signed >= 0.0, signed, np.where(shortable_row, signed, 0.0))
    return kept / np.where(gross > 0.0, gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized hysteretic long/short straddle with a borrow-gated short side."""

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

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :],
            float(enter_bands[ci]), float(exit_bands[ci]), shortable_row,
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
