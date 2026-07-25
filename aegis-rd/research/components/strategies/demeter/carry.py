# %% component overview
# Demeter carry-mix allocator — the SOTA-pole construction sweep from
# [[the-ucits-constrained-carry-sleeve]]. Same two-step routing as demeter.carry (SHAPE =
# inverse-vol across legs, cross-sectional; EXPOSURE = vol-target, time-series), extended
# with the two research-backed SHAPE axes the article seeds:
#
#   - defensive: the maturity-bucket tilt inside the HY sleeve — shifts the HY bucket's
#     inverse-vol weight from broad HY (IHYU) toward short-duration HY (SDHY/STHY), the
#     long-only approximation of a duration strip inside HY (2022 buckets: 0-5yr -5.65%
#     vs >8yr -18.35%). defensive=0 keeps broad HY only; 1.0 replaces it.
#   - fx_weight: a fixed gross share routed to the EM local-currency leg (IEML) — the
#     investable claim on the FX-carry premium WITH its negative skew attached (BIS
#     WP474/775; Burger-Warnock). Modest by design: its diversification is calm-market
#     only (carry drawdowns cluster in recessions — Koijen et al.), which is acceptable
#     for a pole paid to lose then, but it must not be sized as a hedge.
#   - at1_weight: a fixed gross share routed to subordinated bank capital (Invesco AT1,
#     XAT1) — income that is structurally crash-rent (first-loss bank-capital layer), so
#     no tilt can shed its skew ([[the-skew-is-the-product]]). Sized like the fx leg:
#     a satellite share, never a core holding — AT1 events cluster with credit crises.
#
# vol_target is PINNED BY MANDATE (single-value param), not swept: the 2026-07-03 ranker
# A/B showed a swept scale axis feeds mu-estimation noise to a utility ranker; this grid
# sweeps SHAPE only (defensive x fx_weight x at1_weight), which is the grid the
# convergent_income_utility ranker is legitimate on.
#
# Nested control: (defensive=0, fx_weight=0) zero-weights SDHY and IEML, reproducing the
# incumbent IHYU+LQDH inverse-vol book — the sweep contains its own baseline.
# Output gross = exposure <= 1.0, all weights >= 0 (UCITS long-only, no leverage).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.carry_mix",
    "version": "1.2.0",
    "input_names": ["Close"],
    "param_names": ["vol_target", "defensive", "fx_weight", "at1_weight"],
    "output_name": "target_weights",
    "consumes_outputs": ["realized_vol"],
    "defaults": {
        "vol_target": 0.10,
        "defensive": 0.0,
        "fx_weight": 0.0,
        "at1_weight": 0.0,
    },
    "owns_portfolio": False,
}

# Vol floor: keep inverse-vol weights and the vol-target ratio finite (mirrors demeter.carry).
_MIN_VOL = 0.01

# Leg roles by column id (fail-loud). An unlisted column raises rather than being
# weighted with a guessed role.
# The defensive tilt moves weight WITHIN the HY bucket; the IG leg is untouched by it; the
# fx leg is sized by fx_weight alone.
_BROAD_HY = frozenset({"IHYU.L", "IHYU.LSEETF", "HYG", "JNK"})
_DEFENSIVE_HY = frozenset({"SDHY.L", "SDHY.LSEETF", "STHY.L", "STHY.LSEETF"})
_HEDGED_IG = frozenset({"LQDH.L", "LQDH.LSEETF"})
_FX_CARRY = frozenset({"IEML.L", "IEML.LSEETF", "SEML.L", "EMDD.L"})
_SUBORDINATED = frozenset({"XAT1.XBRU", "XAT1.EBS", "XAT1.IBIS2"})


# %% parameter space
def param_space():
    """Return VBT-native params: the SHAPE grid, with the scale axis pinned by mandate.

    ``defensive`` shifts the HY bucket broad -> short-duration; ``fx_weight`` is the EM
    local-currency gross share; ``vol_target`` is a single mandate value, present so it is
    recorded, never swept (the ranker A/B lesson).
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "vol_target": vbt.Param([0.10]),
        "defensive": vbt.Param([0.0, 0.5, 1.0]),
        "fx_weight": vbt.Param([0.0, 0.15, 0.30]),
        "at1_weight": vbt.Param([0.0, 0.10, 0.20]),
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
                f"demeter.carry_mix: {name!r} has no leg role. Add it to _BROAD_HY, "
                f"_DEFENSIVE_HY, _HEDGED_IG, _FX_CARRY or _SUBORDINATED so its tilt is explicit."
            )
    return np.array(tilts), np.array(is_fx), np.array(is_at1)


def _weights(vol_2d, columns, vol_target, defensive, fx_weight, at1_weight):
    """Role-tilted inverse-vol SHAPE x vol-targeted EXPOSURE.

    credit_share_i = tilt_i * (1/vol_i) / sum, scaled to (1 - fx_share - at1_share); the
    fx and at1 satellites each take a fixed gross share (0 while their vol is warming up).
    Rows with no live credit leg are cash. exposure = min(vol_target / sigma_book, 1.0).

    The spread-richness lean (``carry_gain``) was removed in v1.2.0. It was pinned to 0.0 in
    the only live config, which made ``lean`` an array of ones and multiplied the whole
    ``carry_score`` feed straight out - so the champion computed a FRED-backed indicator on
    every run and discarded it. The lean itself was killed empirically on 2026-07-04 (it
    lowered income AND hurt the book), and a knob no live config turns is the free parameter
    this family's design notes argue against.
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

    exposure = np.minimum(vol_target / np.maximum(sigma_book, _MIN_VOL), 1.0)
    exposure = np.where(sigma_book > 0, exposure, 0.0)
    return shares * exposure


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized role-mixed credit book for all candidates."""

    close = inputs.data.array("Close")
    columns = list(close.columns)
    n_symbols = inputs.n_symbols
    T = len(close)

    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)

    # Locks minted before v1.1.0 carry no at1_weight; replaying them means "no AT1 leg".
    at1_list = param_lists.get("at1_weight", [0.0] * n_candidates)

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _weights(
            vol_3d[:, ci, :], columns,
            float(param_lists["vol_target"][ci]),
            float(param_lists["defensive"][ci]),
            float(param_lists["fx_weight"][ci]),
            float(at1_list[ci]),
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
