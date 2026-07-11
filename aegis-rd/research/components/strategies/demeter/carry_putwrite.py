# %% component overview
# Demeter carry-mix with a packaged collateralized put-write satellite. Credit remains an
# inverse-vol book whose exposure may lean on credit richness. E50PW receives a fixed gross
# share and is excluded from the richness mean. putwrite_weight=0 is the nested incumbent.
#
# This standalone variant intentionally leaves the locked carry component untouched. Local
# strategy sources are independently bundled and content-addressed; importing a mutable
# shared role table would couple lock replay to future research variants.

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.carry_mix_putwrite",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": [
        "vol_target",
        "defensive",
        "fx_weight",
        "carry_gain",
        "at1_weight",
        "putwrite_weight",
    ],
    "output_name": "target_weights",
    "consumes_outputs": ["carry_score", "realized_vol"],
    "defaults": {
        "vol_target": 0.10,
        "defensive": 0.0,
        "fx_weight": 0.0,
        "carry_gain": 0.0,
        "at1_weight": 0.0,
        "putwrite_weight": 0.0,
    },
    "owns_portfolio": False,
}

_MIN_VOL = 0.01
_BROAD_HY = frozenset({"IHYU.L", "IHYU.LSEETF", "HYG", "JNK"})
_DEFENSIVE_HY = frozenset({"SDHY.L", "SDHY.LSEETF", "STHY.L", "STHY.LSEETF"})
_HEDGED_IG = frozenset({"LQDH.L", "LQDH.LSEETF"})
_FX_CARRY = frozenset({"IEML.L", "IEML.LSEETF", "SEML.L", "EMDD.L"})
_SUBORDINATED = frozenset({"XAT1.XBRU", "XAT1.EBS", "XAT1.IBIS2"})
_PUTWRITE_CARRY = frozenset({"E50PW.EBS", "E50PW.IBIS", "E50PW.XETR"})


# %% parameter space
def param_space():
    from vectorbtpro import vbt

    return {
        "vol_target": vbt.Param([0.10]),
        "defensive": vbt.Param([0.0, 0.5, 1.0]),
        "fx_weight": vbt.Param([0.0, 0.15, 0.30]),
        "carry_gain": vbt.Param([0.0, 1.0, 2.0]),
        "at1_weight": vbt.Param([0.0, 0.10, 0.20]),
        "putwrite_weight": vbt.Param([0.0, 0.10, 0.20, 0.30]),
    }


# %% lookback
def lookback(**params):
    return 0


# %% helpers
def _leg_roles(columns, defensive):
    tilts, fx, at1, putwrite = [], [], [], []
    for column in columns:
        name = str(column)
        if name in _BROAD_HY:
            role = (1.0 - defensive, False, False, False)
        elif name in _DEFENSIVE_HY:
            role = (defensive, False, False, False)
        elif name in _HEDGED_IG:
            role = (1.0, False, False, False)
        elif name in _FX_CARRY:
            role = (0.0, True, False, False)
        elif name in _SUBORDINATED:
            role = (0.0, False, True, False)
        elif name in _PUTWRITE_CARRY:
            role = (0.0, False, False, True)
        else:
            raise ValueError(f"demeter.carry_mix_putwrite: {name!r} has no explicit leg role")
        tilt, is_fx, is_at1, is_putwrite = role
        tilts.append(tilt)
        fx.append(is_fx)
        at1.append(is_at1)
        putwrite.append(is_putwrite)
    return np.array(tilts), np.array(fx), np.array(at1), np.array(putwrite)


def _weights(
    score_2d,
    vol_2d,
    columns,
    vol_target,
    defensive,
    fx_weight,
    carry_gain,
    at1_weight,
    putwrite_weight,
):
    tilts, is_fx, is_at1, is_putwrite = _leg_roles(columns, defensive)
    vol = np.maximum(vol_2d, _MIN_VOL)
    inv = np.where(np.isfinite(vol_2d), 1.0 / vol, 0.0)
    is_credit = ~(is_fx | is_at1 | is_putwrite)
    credit_raw = inv * tilts[None, :] * is_credit[None, :]
    credit_sum = credit_raw.sum(axis=1, keepdims=True)

    def live_share(mask, weight):
        live = (inv * mask[None, :]).sum(axis=1, keepdims=True) > 0
        return np.where(live, weight, 0.0)

    fx_share = live_share(is_fx, fx_weight)
    at1_share = live_share(is_at1, at1_weight)
    putwrite_share = live_share(is_putwrite, putwrite_weight)
    satellite_share = fx_share + at1_share + putwrite_share
    if np.any(satellite_share > 1.0):
        raise ValueError("demeter.carry_mix_putwrite: satellite weights exceed gross share 1.0")

    shares = np.where(credit_sum > 0, credit_raw / np.where(credit_sum > 0, credit_sum, 1.0), 0.0)
    shares *= 1.0 - satellite_share
    for mask, share in ((is_fx, fx_share), (is_at1, at1_share), (is_putwrite, putwrite_share)):
        shares += np.where((credit_sum > 0) & mask[None, :] & np.isfinite(vol_2d), share, 0.0)

    sigma_book = (shares * vol).sum(axis=1, keepdims=True)
    richness = np.nanmean(np.where(np.isfinite(score_2d), score_2d, np.nan), axis=1, keepdims=True)
    richness = np.where(np.isfinite(richness), np.maximum(richness, 0.0), 0.0)
    lean = np.power(richness, carry_gain) if carry_gain != 0.0 else np.ones_like(richness)
    exposure = np.minimum(vol_target / np.maximum(sigma_book, _MIN_VOL) * lean, 1.0)
    exposure = np.where(sigma_book > 0, exposure, 0.0)
    return shares * exposure


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Allocate the credit book and explicit put-write satellite for all candidates."""

    close = inputs.data.array("Close")
    columns = list(close.columns)
    n_symbols = inputs.n_symbols
    periods = len(close)
    scores = inputs.indicators["carry_score"].reshape(periods, n_candidates, n_symbols)
    vols = inputs.indicators["realized_vol"].reshape(periods, n_candidates, n_symbols)
    at1_values = param_lists.get("at1_weight", [0.0] * n_candidates)
    putwrite_values = param_lists.get("putwrite_weight", [0.0] * n_candidates)
    result = np.full((periods, n_candidates, n_symbols), np.nan)
    for candidate in range(n_candidates):
        result[:, candidate, :] = _weights(
            scores[:, candidate, :],
            vols[:, candidate, :],
            columns,
            float(param_lists["vol_target"][candidate]),
            float(param_lists["defensive"][candidate]),
            float(param_lists["fx_weight"][candidate]),
            float(param_lists["carry_gain"][candidate]),
            float(at1_values[candidate]),
            float(putwrite_values[candidate]),
        )
    return result.reshape(periods, n_candidates * n_symbols)
