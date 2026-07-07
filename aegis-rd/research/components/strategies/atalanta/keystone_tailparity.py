# %% component overview
# Atalanta KEYSTONE + TAIL-RISK-PARITY SIZING (atalanta.keystone_tailparity, aegis-rd campaign,
# GH #80) - the champion keystone_shortmute with ONE change: the risk denominator that normalizes
# each leg's trend-magnitude weight is blended from inverse-VOL toward inverse-EXPECTED-SHORTFALL.
#
#   risk_i = max(vol_i, floor)^(1 - tilt) * max(ES_i, floor)^(tilt)      tilt in [0, 1]
#   long_leg_i = max(score_i, 0) / risk_i        (short legs the same, as in the champion)
#
# The champion sizes each leg by max(score,0)/vol (inverse-vol parity): a 1%/day and a 3%/day leg
# contribute comparable *volatility*. Tail-risk parity instead sizes by inverse Expected Shortfall,
# so legs contribute comparable *left-tail* risk - down-weighting fat-left-tail / negatively-skewed
# legs relative to their inverse-vol weight (AllianceBernstein "An Introduction to Tail Risk Parity";
# Boudt et al. 2013 CVaR risk budgeting; the ERC-ES thesis showing lower realized MaxDD/downside-vol
# than vol-ERC). The hypothesis ([[budgeting-the-divergent-seat]]): for a FLOOR sleeve whose binding
# constraint is its own worst-split drawdown (the gate that killed the levered pyramid), equalizing
# TAIL risk rather than volatility lowers the left tail at held-out convexity parity or better.
#
# tilt is the ONLY swept lever. tilt = 0 -> risk_i = vol_i EXACTLY -> reproduces keystone_shortmute
# byte-for-byte (the nested champion control; ES^0 = 1, vol^1 = vol). tilt = 1 -> pure inverse-ES.
# For a Gaussian leg ES = vol x const, so the common scale cancels under gross-normalization and the
# tilt bites ONLY through each leg's downside non-normality - if the three curated legs are near-
# Gaussian in the left tail the lever is near-inert, which is itself the finding. Bands and short_cap
# are pinned to the champion; the borrow-gated one-sided short mute is carried unchanged.
#
# Live-research parity: ES is a causal trailing-window indicator (atalanta.realized_shortfall); the
# blend and gross-normalization are the champion's, so the live path recomputes the identical target.

# %% imports
import numpy as np
import pandas as pd

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.keystone_tailparity",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["enter_band", "exit_band", "short_cap", "tilt"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol", "realized_shortfall"],
    "defaults": {"enter_band": 0.10, "exit_band": 0.05, "short_cap": 1.0, "tilt": 0.0},
    "owns_portfolio": False,
}

# Risk floor: below this the inverse-risk weight is capped (matches the champion's _MIN_VOL).
_MIN_RISK = 0.01

# The SHORT whitelist: the inflation-crisis short-bond leg only (identical to keystone_shortmute).
_BORROWABLE = frozenset({"IDTL", "TLT", "SPTL", "EDV"})


# %% parameter space
def param_space():
    """Champion bands + short cap pinned; the inverse-vol -> inverse-ES ``tilt`` is the swept lever.

    ``tilt`` blends the risk denominator geometrically from vol (0) to Expected Shortfall (1). 0.0 is
    the nested champion control (risk = vol exactly); the active values trace how far toward pure
    tail-parity the sleeve wants to sit. A single swept axis keeps mu-noise off the ranker; the
    shortfall window/alpha are pinned on the indicator side.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "enter_band": vbt.Param([0.10]),
        "exit_band": vbt.Param([0.05]),
        "short_cap": vbt.Param([0.10]),  # champion's promoted value
        "tilt": vbt.Param([0.0, 0.33, 0.66, 1.0]),  # 0.0 = inverse-vol (champion control)
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

    Identical to the champion: +1 once score > +enter_band, -1 once score < -exit_band; otherwise
    carry the last state forward. NaN (warmup) and rows before the first breach read as flat (0).
    """

    signal = np.where(score_2d > enter_band, 1.0, np.where(score_2d < -exit_band, -1.0, np.nan))
    state = pd.DataFrame(signal).ffill().to_numpy()
    return np.where(np.isfinite(state), state, 0.0)


def _blended_risk(vol_2d, es_2d, tilt):
    """Geometric blend of the risk denominator: vol^(1-tilt) * ES^tilt, floored.

    ``tilt = 0`` returns vol exactly (the champion); ``tilt = 1`` returns ES (pure tail parity). ES
    NaN during warmup propagates to NaN risk, which the score gate zeroes out just as for vol.
    """

    vol = np.maximum(vol_2d, _MIN_RISK)
    es = np.maximum(es_2d, _MIN_RISK)
    if tilt <= 0.0:
        return vol
    if tilt >= 1.0:
        return es
    return vol ** (1.0 - tilt) * es ** tilt


def _candidate_weights(score_2d, vol_2d, es_2d, enter_band, exit_band, short_cap, tilt, shortable_row):
    """Champion hysteretic FORGO weights, the inverse-vol risk denominator replaced by the blend.

    Every place the champion divides by ``vol`` this divides by ``risk = vol^(1-tilt) * ES^tilt``;
    at ``tilt = 0`` risk == vol so the book is byte-identical to keystone_shortmute. The gross divisor
    is taken from the UNCAPPED signed book (champion semantics), so the one-sided short mute still
    drops its freed gross to cash.
    """

    risk = _blended_risk(vol_2d, es_2d, tilt)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    state = _hysteretic_state(score_2d, enter_band, exit_band)

    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / risk
    short_full = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / risk
    gross = np.abs(long_leg - short_full).sum(axis=1, keepdims=True)  # champion (uncapped) gross

    short_muted = np.where(state < 0.0, np.minimum(np.maximum(-score, 0.0), short_cap), 0.0) / risk
    signed = long_leg - short_muted
    kept = np.where(signed >= 0.0, signed, np.where(shortable_row, signed, 0.0))
    return kept / np.where(gross > 0.0, gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized hysteretic L/S straddle (borrow-gated short, one-sided short cap) with the risk
    denominator blended from inverse-vol toward inverse-Expected-Shortfall (tail-risk parity)."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    shortable_row = np.array([[_base_symbol(c) in _BORROWABLE for c in close.columns]], dtype=bool)

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    es_3d = inputs.indicators["realized_shortfall"].reshape(T, n_candidates, n_symbols)
    enter_bands = param_lists["enter_band"]
    exit_bands = param_lists["exit_band"]
    short_caps = param_lists["short_cap"]
    tilts = param_lists["tilt"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], es_3d[:, ci, :],
            float(enter_bands[ci]), float(exit_bands[ci]), float(short_caps[ci]),
            float(tilts[ci]), shortable_row,
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
