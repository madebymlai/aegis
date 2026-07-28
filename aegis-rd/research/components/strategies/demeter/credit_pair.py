# %% component overview
# Demeter currency-clean credit pair - the convergent pole rebuilt on EUR-denominated legs.
#
# WHY A NEW COMPONENT. demeter.carry_mix routes USD-denominated legs (SDHY, LQDH) into a
# EUR book. Measured 2026-07-25 on total return rebuilt from the catalog distribution
# store, FX is 68% of SDHY's and 57% of LQDH's EUR-investor variance: EURUSD runs 7.2%/yr
# against 6.6-7.1%/yr of credit, so roughly two thirds of the pole's risk was a currency
# bet with no expected return. The same measurement found the two legs correlate +0.75 in
# EUR terms - the "two-leg diversified credit sleeve" was substantially one bet wearing a
# shared dollar. carry_mix stays live and replayable until this challenger beats it.
#
# THE LEGS, all EUR-denominated so the book needs no FX conversion at all:
#
#   - US short-maturity HY (PIMCO STHE, ICE BofA US HY Constrained 0-5yr, EUR-HEDGED
#     share class of the fund [[the-ucits-constrained-carry-sleeve]] already names as the
#     co-equal expression of "defensive inside HY"). This is a SHARE-CLASS change within
#     the article's own shortlist, not a new instrument hypothesis.
#   - EUR-native HY (iShares IHYG, iBoxx EUR Liquid HY). A SECOND credit market rather
#     than a second slice of the same one: European issuers, a different default cycle,
#     and naturally short duration (~2.4-3.0yr) because European HY issues short - so the
#     maturity-bucket discipline the article demands comes structurally rather than by
#     tilt.
#   - EUR IG with the rates stripped (iShares IRCP, which subtracts a monthly basket of
#     GERMAN government bond futures - the EUR analogue of LQDH selling US Treasuries).
#     The article's instrument survey recorded the rate-hedged wrapper as existing "for
#     IG (LQDH)" and did not have a EUR one; it does exist.
#   - Subordinated bank capital (Invesco XAT1) stays a supported role for the separate
#     satellite sweep. It is EUR-hedged already, so it needs no currency work.
#
# SHAPE AXIS. carry_mix hard-coded inverse-vol weighting. Measured, that hands the
# low-vol IG leg 66-73% of the sleeve - the IG leg silently BECOMES the sleeve. So the
# weighting rule is swept rather than assumed: weight_i is proportional to
# tilt_i * (1/vol_i) ** shape_power, where shape_power=0 is tilt-weighted equal and
# shape_power=1 reproduces carry_mix's inverse-vol.
#
# SCALE IS DELIBERATELY UNCHANGED. exposure = min(vol_target / sigma_book, 1.0) is carried
# over verbatim even though it binds on 81-94% of days and the book allocator already
# vol-targets and levers to gross_cap 1.75. Dropping it is a well-motivated separate
# experiment (the article's own cited evidence has vol-managing HY buying Sharpe by
# reducing the negative skew, which for a pole hired to be concave is paying out of the
# skew inventory) - bundling it into a universe swap would confound the two changes.
#
# Output gross = exposure <= 1.0, all weights >= 0 (UCITS long-only, no leverage).

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.credit_pair",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["vol_target", "shape_power", "eur_hy_share", "at1_weight"],
    "output_name": "target_weights",
    "consumes_outputs": ["realized_vol"],
    "defaults": {
        "vol_target": 0.10,
        "shape_power": 1.0,
        "eur_hy_share": 0.0,
        "at1_weight": 0.0,
    },
    "owns_portfolio": False,
}

# Vol floor: keep the shape weights and the vol-target ratio finite (mirrors carry_mix).
_MIN_VOL = 0.01

# Leg roles by column id (fail-loud). An unlisted column raises rather than being weighted
# with a guessed role. Every id here is EUR-denominated - that is the point of the
# component, so a USD line landing in one of these sets would be a bug, not a variant.
_US_HY_SHORT = frozenset({"STHE.LSEETF", "STHE.EBS", "STHE.BVME.ETF"})
_EUR_HY = frozenset({"IHYG.LSEETF", "IHYG.EBS", "XHYG.IBIS2"})
_HEDGED_IG = frozenset({"IRCP.LSEETF", "IRCP.EBS"})
_SUBORDINATED = frozenset({"XAT1.XBRU", "XAT1.EBS", "XAT1.IBIS2"})


# %% parameter space
def param_space():
    """Return VBT-native params: SHAPE axes only, with the scale axis pinned by mandate.

    ``shape_power`` is the weighting rule (0 = tilt-weighted equal, 1 = inverse vol);
    ``eur_hy_share`` splits the HY bucket between US short-maturity and EUR-native;
    ``at1_weight`` is the subordinated satellite, swept separately. ``vol_target`` is a
    single mandate value, present so it is recorded, never swept (the ranker A/B lesson:
    a free scale axis feeds mu-estimation noise to a utility ranker).
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "vol_target": vbt.Param([0.10]),
        "shape_power": vbt.Param([0.0, 1.0]),
        "eur_hy_share": vbt.Param([0.0, 0.5, 1.0]),
        "at1_weight": vbt.Param([0.0]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators': mixing and vol-targeted sizing add none."""
    return 0


# %% helpers
def _leg_tilts(columns, eur_hy_share):
    """Per-column (core_tilt, is_at1) from the leg-role sets. Unknown column raises.

    ``eur_hy_share`` moves weight WITHIN the HY bucket from US short-maturity toward
    EUR-native; the rate-hedged IG leg is untouched by it, and the subordinated leg is
    sized by ``at1_weight`` alone.
    """

    tilts, is_at1 = [], []
    for col in columns:
        name = str(col)
        if name in _US_HY_SHORT:
            tilts.append(1.0 - eur_hy_share)
            is_at1.append(False)
        elif name in _EUR_HY:
            tilts.append(eur_hy_share)
            is_at1.append(False)
        elif name in _HEDGED_IG:
            tilts.append(1.0)
            is_at1.append(False)
        elif name in _SUBORDINATED:
            tilts.append(0.0)
            is_at1.append(True)
        else:
            raise ValueError(
                f"demeter.credit_pair: {name!r} has no leg role. Add it to _US_HY_SHORT, "
                f"_EUR_HY, _HEDGED_IG or _SUBORDINATED so its tilt is explicit. Every leg "
                f"in this component is EUR-denominated by design."
            )
    return np.array(tilts), np.array(is_at1)


def _weights(vol_2d, columns, vol_target, shape_power, eur_hy_share, at1_weight):
    """Role-tilted SHAPE x vol-targeted EXPOSURE.

    core_share_i = tilt_i * (1/vol_i)**shape_power / sum, scaled to (1 - at1_share); the
    subordinated satellite takes a fixed gross share (0 while its vol is warming up).
    Rows with no live core leg are cash. exposure = min(vol_target / sigma_book, 1.0).
    """

    tilts, is_at1 = _leg_tilts(columns, eur_hy_share)
    vol = np.maximum(vol_2d, _MIN_VOL)
    live = np.isfinite(vol_2d)
    # shape_power=0 gives every live leg the same 1.0 factor, so the tilts alone decide.
    shape = np.where(live, np.power(1.0 / vol, shape_power), 0.0)

    is_core = ~is_at1
    core_raw = shape * tilts[None, :] * is_core[None, :]
    core_sum = core_raw.sum(axis=1, keepdims=True)

    at1_live = (shape * is_at1[None, :]).sum(axis=1, keepdims=True) > 0
    at1_share = np.where(at1_live, at1_weight, 0.0)

    shares = np.where(core_sum > 0, core_raw / np.where(core_sum > 0, core_sum, 1.0), 0.0)
    shares = shares * (1.0 - at1_share)
    shares = shares + np.where((core_sum > 0) & is_at1[None, :] & live, at1_share, 0.0)

    sigma_book = (shares * vol).sum(axis=1, keepdims=True)  # comonotone approx

    exposure = np.minimum(vol_target / np.maximum(sigma_book, _MIN_VOL), 1.0)
    exposure = np.where(sigma_book > 0, exposure, 0.0)
    return shares * exposure


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized role-mixed EUR credit book for all candidates."""

    close = inputs.data.array("Close")
    columns = list(close.columns)
    n_symbols = inputs.n_symbols
    T = len(close)

    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _weights(
            vol_3d[:, ci, :],
            columns,
            float(param_lists["vol_target"][ci]),
            float(param_lists["shape_power"][ci]),
            float(param_lists["eur_hy_share"][ci]),
            float(param_lists["at1_weight"][ci]),
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
