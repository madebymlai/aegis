# %% component overview
# Demeter carry-mix allocator, COMMODITY-BREADTH variant (aegis-rd-bkom) — demeter.carry_mix
# extended with one market-neutral commodity-carry breadth leg (UBS CMCI Commodity Carry SF
# UCITS ETF, UEQC). The leg is a SATELLITE, modelled exactly like the existing fx and at1
# legs: a fixed gross share (commodity_weight), tilt 0.0, carved out of the credit
# inverse-vol book, and EXCLUDED from the spread-richness exposure lean (it carries no
# credit spread — its carry_score is NaN from demeter_eu.credit_carry_commodity, so the
# credit-only richness mean already drops it).
#
# Why a breadth share and not a scored leg: UEQC is itself a packaged market-neutral
# commodity-carry STRATEGY wrapped in an accumulating ETF, so holding it long IS the carry
# expression (as holding IHYU long IS the credit-carry expression). There is no per-name
# commodity spread to score cross-sectionally; the research question (aegis-rd-bkom) is
# whether a fixed ~15-25% breadth allocation lifts the concave pole's income Sharpe while
# its robust downside L-skew stays < 0 (the leg mutes but must not breach the concave gate).
#
# Nested control: commodity_weight=0 zero-weights UEQC and reproduces demeter.carry_mix
# exactly — the sweep contains its own in-grid baseline (the 0-cell), judged against which
# (not the different-window champion lock) because UEQC's history starts 2020-01-23.
# Output gross = exposure <= 1.0, all weights >= 0 (UCITS long-only, no leverage).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.carry_mix_commodity",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["vol_target", "defensive", "fx_weight", "carry_gain", "at1_weight", "commodity_weight"],
    "output_name": "target_weights",
    "consumes_outputs": ["carry_score", "realized_vol"],
    "defaults": {
        "vol_target": 0.10,
        "defensive": 0.0,
        "fx_weight": 0.0,
        "carry_gain": 0.0,
        "at1_weight": 0.0,
        "commodity_weight": 0.0,
    },
    "owns_portfolio": False,
}

# Vol floor: keep inverse-vol weights and the vol-target ratio finite (mirrors demeter.carry).
_MIN_VOL = 0.01

# Leg roles by column id (fail-loud, mirroring demeter_eu.credit_carry_commodity).
_BROAD_HY = frozenset({"IHYU.L", "IHYU.LSEETF", "HYG", "JNK"})
_DEFENSIVE_HY = frozenset({"SDHY.L", "SDHY.LSEETF", "STHY.L", "STHY.LSEETF"})
_HEDGED_IG = frozenset({"LQDH.L", "LQDH.LSEETF"})
_FX_CARRY = frozenset({"IEML.L", "IEML.LSEETF", "SEML.L", "EMDD.L"})
_SUBORDINATED = frozenset({"XAT1.XBRU", "XAT1.EBS", "XAT1.IBIS2"})
_COMMODITY_CARRY = frozenset({"UEQC.IBIS", "UEQC.XETR"})


# %% parameter space
def param_space():
    """Return VBT-native params: the SHAPE grid plus the commodity breadth-share axis.

    ``commodity_weight`` is the only axis this experiment sweeps ({0, 0.15, 0.25}); the
    other SHAPE axes are pinned to the champion floor-partner cell in the run config, so
    the grid collapses to a single-change sweep (the aegis-rd-bkom keep/kill). vol_target
    is a single mandate value, recorded but never swept (the ranker A/B lesson).
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "vol_target": vbt.Param([0.10]),
        "defensive": vbt.Param([0.0, 0.5, 1.0]),
        "fx_weight": vbt.Param([0.0, 0.15, 0.30]),
        "carry_gain": vbt.Param([0.0, 1.0, 2.0]),
        "at1_weight": vbt.Param([0.0, 0.10, 0.20]),
        "commodity_weight": vbt.Param([0.0, 0.15, 0.25]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators': mixing and vol-targeted sizing add none."""
    return 0


# %% helpers
def _leg_tilts(columns, defensive):
    """Per-column (credit_tilt, is_fx, is_at1, is_commodity) from the leg-role sets.

    Unknown column raises (fail-loud). The commodity leg is tilt 0.0 like the fx/at1
    satellites: it is not part of the credit inverse-vol book, only a fixed gross share.
    """

    tilts, is_fx, is_at1, is_commodity = [], [], [], []
    for col in columns:
        name = str(col)
        if name in _BROAD_HY:
            tilts.append(1.0 - defensive); is_fx.append(False); is_at1.append(False); is_commodity.append(False)
        elif name in _DEFENSIVE_HY:
            tilts.append(defensive); is_fx.append(False); is_at1.append(False); is_commodity.append(False)
        elif name in _HEDGED_IG:
            tilts.append(1.0); is_fx.append(False); is_at1.append(False); is_commodity.append(False)
        elif name in _FX_CARRY:
            tilts.append(0.0); is_fx.append(True); is_at1.append(False); is_commodity.append(False)
        elif name in _SUBORDINATED:
            tilts.append(0.0); is_fx.append(False); is_at1.append(True); is_commodity.append(False)
        elif name in _COMMODITY_CARRY:
            tilts.append(0.0); is_fx.append(False); is_at1.append(False); is_commodity.append(True)
        else:
            raise ValueError(
                f"demeter.carry_mix_commodity: {name!r} has no leg role. Add it to _BROAD_HY, "
                f"_DEFENSIVE_HY, _HEDGED_IG, _FX_CARRY, _SUBORDINATED or _COMMODITY_CARRY."
            )
    return np.array(tilts), np.array(is_fx), np.array(is_at1), np.array(is_commodity)


def _weights(
    score_2d, vol_2d, columns, vol_target, defensive, fx_weight, carry_gain, at1_weight, commodity_weight
):
    """Role-tilted inverse-vol SHAPE x vol-targeted, richness-leaned EXPOSURE.

    Identical to demeter.carry_mix except a third satellite share: the fx, at1 and commodity
    legs each take a fixed gross share (0 while their vol warms up), and the credit book
    scales to (1 - fx_share - at1_share - commodity_share). The commodity leg is excluded
    from the spread-richness lean (its score is NaN, so the nanmean already drops it).
    exposure = min(vol_target / sigma_book * richness^carry_gain, 1.0).
    """

    tilts, is_fx, is_at1, is_commodity = _leg_tilts(columns, defensive)
    vol = np.maximum(vol_2d, _MIN_VOL)
    inv = np.where(np.isfinite(vol_2d), 1.0 / vol, 0.0)

    is_credit = ~(is_fx | is_at1 | is_commodity)
    credit_raw = inv * tilts[None, :] * is_credit[None, :]
    credit_sum = credit_raw.sum(axis=1, keepdims=True)

    fx_live = (inv * is_fx[None, :]).sum(axis=1, keepdims=True) > 0
    fx_share = np.where(fx_live, fx_weight, 0.0)
    at1_live = (inv * is_at1[None, :]).sum(axis=1, keepdims=True) > 0
    at1_share = np.where(at1_live, at1_weight, 0.0)
    commodity_live = (inv * is_commodity[None, :]).sum(axis=1, keepdims=True) > 0
    commodity_share = np.where(commodity_live, commodity_weight, 0.0)

    shares = np.where(credit_sum > 0, credit_raw / np.where(credit_sum > 0, credit_sum, 1.0), 0.0)
    shares = shares * (1.0 - fx_share - at1_share - commodity_share)
    shares = shares + np.where(
        (credit_sum > 0) & is_fx[None, :] & np.isfinite(vol_2d), fx_share, 0.0
    )
    shares = shares + np.where(
        (credit_sum > 0) & is_at1[None, :] & np.isfinite(vol_2d), at1_share, 0.0
    )
    shares = shares + np.where(
        (credit_sum > 0) & is_commodity[None, :] & np.isfinite(vol_2d), commodity_share, 0.0
    )

    sigma_book = (shares * vol).sum(axis=1, keepdims=True)  # comonotone approx

    richness = np.nanmean(np.where(np.isfinite(score_2d), score_2d, np.nan), axis=1, keepdims=True)
    richness = np.where(np.isfinite(richness), np.maximum(richness, 0.0), 0.0)
    lean = np.power(richness, carry_gain) if carry_gain != 0.0 else np.ones_like(richness)

    exposure = np.minimum(vol_target / np.maximum(sigma_book, _MIN_VOL) * lean, 1.0)
    exposure = np.where(sigma_book > 0, exposure, 0.0)
    return shares * exposure


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized role-mixed credit book with a commodity breadth satellite, all candidates."""

    close = inputs.data.array("Close")
    columns = list(close.columns)
    n_symbols = inputs.n_symbols
    T = len(close)

    score_3d = inputs.indicators["carry_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)

    # Locks minted before this variant carry no at1/commodity axis; absent -> "no such leg".
    at1_list = param_lists.get("at1_weight", [0.0] * n_candidates)
    commodity_list = param_lists.get("commodity_weight", [0.0] * n_candidates)

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], columns,
            float(param_lists["vol_target"][ci]),
            float(param_lists["defensive"][ci]),
            float(param_lists["fx_weight"][ci]),
            float(param_lists["carry_gain"][ci]),
            float(at1_list[ci]),
            float(commodity_list[ci]),
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
