# %% component overview
# Demeter carry-mix allocator, UNCLIPPED (aegis-rd-0osb) — demeter.carry_mix with the
# gross <= 1.0 exposure clamp replaced by a pinned ``max_gross`` ceiling. Same two-step
# routing (SHAPE = role-tilted inverse-vol, cross-sectional; EXPOSURE = vol-target x
# spread-richness lean, time-series); the ONLY change is the clamp:
#
#   exposure = min(vol_target / sigma_book * lean, max_gross)     # was: min(..., 1.0)
#
# Why: with vol_target 0.10 and sigma_book ~0.04-0.06 the raw scale sits at ~1.7-2.5, so
# the old clamp bound almost every bar — the sleeve ran as "fully invested except crisis
# de-risk" and the top half of its own vol-targeting signal was discarded. Unclipping
# makes the vol-targeting two-sided: levered when calm, de-risked when stressed. Margin
# interest on the borrow is priced by the sim (margin_interest_rate, default = the pinned
# IBKR-IE EUR blend), so the timing gain competes against its funding bill honestly.
#
# The old header's "UCITS long-only, no leverage" clamp rationale was stale: UCITS
# constrains the FUNDS (the ETFs internally), not account-level margin on their holder —
# the clamp was a design choice, corrected here. Long-only is kept: all weights >= 0.
#
# max_gross is PINNED BY MANDATE (single value, never swept, never chosen by scanning
# results): 2.0, the research-validated cap ceiling the bundles carry (B1, GH #79/#80).
# vol_target stays PINNED at 0.10 for the same reason as the parent (the 2026-07-03
# ranker A/B: a swept scale axis feeds mu-estimation noise to the utility ranker; this
# grid sweeps SHAPE only).
#
# Nested control: max_gross=1.0 reproduces demeter.carry_mix exactly (it is the manifest
# default, so an absent param replays the incumbent clamp).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.carry_mix_unclipped",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["vol_target", "defensive", "fx_weight", "carry_gain", "at1_weight", "max_gross"],
    "output_name": "target_weights",
    "consumes_outputs": ["carry_score", "realized_vol"],
    "defaults": {
        "vol_target": 0.10,
        "defensive": 0.0,
        "fx_weight": 0.0,
        "carry_gain": 0.0,
        "at1_weight": 0.0,
        "max_gross": 1.0,
    },
    "owns_portfolio": False,
}

# Vol floor: keep inverse-vol weights and the vol-target ratio finite (mirrors demeter.carry).
_MIN_VOL = 0.01

# Leg roles by column id (fail-loud, mirroring demeter.carry_mix).
_BROAD_HY = frozenset({"IHYU.L", "IHYU.LSEETF", "HYG", "JNK"})
_DEFENSIVE_HY = frozenset({"SDHY.L", "SDHY.LSEETF", "STHY.L", "STHY.LSEETF"})
_HEDGED_IG = frozenset({"LQDH.L", "LQDH.LSEETF"})
_FX_CARRY = frozenset({"IEML.L", "IEML.LSEETF", "SEML.L", "EMDD.L"})
_SUBORDINATED = frozenset({"XAT1.XBRU", "XAT1.EBS", "XAT1.IBIS2"})


# %% parameter space
def param_space():
    """Return VBT-native params: the SHAPE grid, with both scale axes pinned by mandate.

    ``vol_target`` and ``max_gross`` are single mandate values, present so they are
    recorded, never swept (the ranker A/B lesson applies to any scale axis, including
    the ceiling).
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "vol_target": vbt.Param([0.10]),
        "defensive": vbt.Param([0.0, 0.5, 1.0]),
        "fx_weight": vbt.Param([0.0, 0.15, 0.30]),
        "carry_gain": vbt.Param([0.0, 1.0, 2.0]),
        "at1_weight": vbt.Param([0.0, 0.10, 0.20]),
        "max_gross": vbt.Param([2.0]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators': mixing and vol-targeted sizing add none."""
    return 0


# %% helpers
def _leg_tilts(columns, defensive):
    """Per-column (credit_tilt, is_fx, is_at1) from the leg-role sets. Unknown column raises."""

    tilts, is_fx, is_at1 = [], [], []
    for col in columns:
        name = str(col)
        if name in _BROAD_HY:
            tilts.append(1.0 - defensive)
            is_fx.append(False)
            is_at1.append(False)
        elif name in _DEFENSIVE_HY:
            tilts.append(defensive)
            is_fx.append(False)
            is_at1.append(False)
        elif name in _HEDGED_IG:
            tilts.append(1.0)
            is_fx.append(False)
            is_at1.append(False)
        elif name in _FX_CARRY:
            tilts.append(0.0)
            is_fx.append(True)
            is_at1.append(False)
        elif name in _SUBORDINATED:
            tilts.append(0.0)
            is_fx.append(False)
            is_at1.append(True)
        else:
            raise ValueError(
                f"demeter.carry_mix_unclipped: {name!r} has no leg role. Add it to _BROAD_HY, "
                f"_DEFENSIVE_HY, _HEDGED_IG, _FX_CARRY or _SUBORDINATED so its tilt is explicit."
            )
    return np.array(tilts), np.array(is_fx), np.array(is_at1)


def _weights(
    score_2d, vol_2d, columns, vol_target, defensive, fx_weight, carry_gain, at1_weight, max_gross
):
    """Role-tilted inverse-vol SHAPE x vol-targeted, richness-leaned EXPOSURE.

    Identical to demeter.carry_mix except the exposure ceiling:
    exposure = min(vol_target / sigma_book * richness^carry_gain, max_gross).
    """

    tilts, is_fx, is_at1 = _leg_tilts(columns, defensive)
    vol = np.maximum(vol_2d, _MIN_VOL)
    inv = np.where(np.isfinite(vol_2d), 1.0 / vol, 0.0)

    is_credit = ~(is_fx | is_at1)
    credit_raw = inv * tilts[None, :] * is_credit[None, :]
    credit_sum = credit_raw.sum(axis=1, keepdims=True)

    fx_live = (inv * is_fx[None, :]).sum(axis=1, keepdims=True) > 0
    fx_share = np.where(fx_live, fx_weight, 0.0)
    at1_live = (inv * is_at1[None, :]).sum(axis=1, keepdims=True) > 0
    at1_share = np.where(at1_live, at1_weight, 0.0)

    shares = np.where(credit_sum > 0, credit_raw / np.where(credit_sum > 0, credit_sum, 1.0), 0.0)
    shares = shares * (1.0 - fx_share - at1_share)
    shares = shares + np.where(
        (credit_sum > 0) & is_fx[None, :] & np.isfinite(vol_2d), fx_share, 0.0
    )
    shares = shares + np.where(
        (credit_sum > 0) & is_at1[None, :] & np.isfinite(vol_2d), at1_share, 0.0
    )

    sigma_book = (shares * vol).sum(axis=1, keepdims=True)  # comonotone approx

    richness = np.nanmean(np.where(np.isfinite(score_2d), score_2d, np.nan), axis=1, keepdims=True)
    richness = np.where(np.isfinite(richness), np.maximum(richness, 0.0), 0.0)
    lean = np.power(richness, carry_gain) if carry_gain != 0.0 else np.ones_like(richness)

    exposure = np.minimum(vol_target / np.maximum(sigma_book, _MIN_VOL) * lean, max_gross)
    exposure = np.where(sigma_book > 0, exposure, 0.0)
    return shares * exposure


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized role-mixed credit book for all candidates."""

    close = inputs.data.array("Close")
    columns = list(close.columns)
    n_symbols = inputs.n_symbols
    T = len(close)

    score_3d = inputs.indicators["carry_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)

    at1_list = param_lists.get("at1_weight", [0.0] * n_candidates)
    max_gross_list = param_lists.get("max_gross", [1.0] * n_candidates)

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], columns,
            float(param_lists["vol_target"][ci]),
            float(param_lists["defensive"][ci]),
            float(param_lists["fx_weight"][ci]),
            float(param_lists["carry_gain"][ci]),
            float(at1_list[ci]),
            float(max_gross_list[ci]),
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
