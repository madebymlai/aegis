# %% component overview
# Atalanta KEYSTONE + LEVERED EXTENSION PYRAMIDING (aegis-rd campaign, GH #80) - the champion
# shortmute keystone with the LITERATURE-SHAPED pyramid: every trend leg enters at FULL champion
# size, and ADDS financed exposure on top as the open trade extends in its own direction
# (vol-normalized units since the latch entry), capped at pyr_cap x the champion weight.
#
#   m = 1 + (pyr_cap - 1) * clip(r / pyr_k, 0, 1)      r = favorable extension / annualized vol
#   weights = (champion signed book * m) / champion gross divisor
#
# HOW THIS DIFFERS from the ARCHIVED atalanta.keystone_pyramid (killed 2026-07-03): that variant
# was the leverage-free INVERSION - fresh trends started at pyr_floor ~ 0 and only BUILT TO the
# champion weight, so it under-participated the front of every move; the kill diagnosis was
# exactly that lag ("the ramp's delay misses the convex front", monotone convexity destruction
# 0.4474 -> 0.35 -> 0.235). This variant keeps the champion's front-loading byte-intact (m >= 1
# always: at entry m = 1, the leg IS the champion leg) and expresses the pyramid the way the
# sources define it - Mulvaney's tranche multiplier m = min(cap, 1 + r/K) on open-trade profit
# over initial risk (Concretum's replica: trade skew ~5.8, the right tail IS the added tranches);
# Concretum VPP: "additional units added at predefined profit thresholds", capped at 4x, best
# Profit Factor of the sizing family (1.74 vs 1.55 unpyramided) by "amplifying exposure to the
# right tail"; CFM: building into extended trends is how the convex right tail is manufactured.
# The known cost, also from the literature: "added risk is given back if the trade reverses" -
# reversal give-back on the largest position - plus margin interest on the added gross, which the
# sim now prices (margin_interest_rate, IBKR-IE first tier). The kill's mechanism cannot recur
# (nothing is held back); the NEW failure modes under test are give-back + funding.
#
# pyr_cap is PINNED BY MANDATE at 2.0 - the research-validated cap ceiling (B1) - never swept,
# never chosen from results (the literature's 4x does not fit the caps and is not attempted).
# The ramp is CONTINUOUS rather than discrete layers: the drift band already suppresses small
# rebalances, and a stepped m would fight it with burst turnover at each layer boundary.
# pyr_k <= 0 disables the ramp (m = 1 everywhere) -> reproduces keystone_shortmute EXACTLY (the
# nested champion control). The borrow-gated short leg ramps symmetrically; short_cap untouched.
#
# v1.1.0 - THE GIVE-BACK TRAILING STOP (aegis-rd re-entry, GH #80): v1.0.0's grid was KILLED on
# survivability only (2026-07-06): the shape WORKED - convexity DOUBLED (0.966 vs the champion's
# 0.445) - but worst-split maxDD ran 1.84-1.94x the champion vs a 1.5x floor-mandate bar, because
# the diagnosis was clean: dd scaled with the added gross and the literature's own cost ("added
# risk is given back if the trade reverses") plays out as a linear ramp-DOWN that is too slow -
# at an extension PEAK the leg carries pyr_cap x gross, and a sharp reversal eats the drawdown on
# that levered position before ``ext`` shrinks enough to unwind it. ``give_back`` is a high-water-
# mark trailing stop on the ADDED tranche only: track each leg's peak favorable extension, and
# once the trade retraces ``give_back`` vol-units BELOW that peak, snap the multiplier back to 1
# (champion size, pyramid OFF) for the remainder of the leg - a latched give-back that caps the
# peak-to-trough bleed of the tranche instead of riding it linearly down. It arms only after the
# leg has actually pyramided (peak extension > 0), so an early adverse wobble does not disarm a
# fresh leg. This BENDS the dose: full convexity on the way up, stop-limited give-back on the way
# down. ``give_back <= 0`` disables the stop -> reproduces the v1.0.0 levered pyramid EXACTLY (the
# nested killed-dose control). The stop is deliberately LATCHING (no re-pyramiding into a tired leg
# after a stop-out until a sign flip starts a new leg) - the conservative choice for a floor sleeve;
# a re-arming variant is a follow-up, not this run.

# %% imports
import numpy as np
import pandas as pd

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.keystone_pyramid_levered",
    "version": "1.1.0",
    "input_names": ["Close"],
    "param_names": ["enter_band", "exit_band", "short_cap", "pyr_k", "pyr_cap", "give_back"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"enter_band": 0.10, "exit_band": 0.05, "short_cap": 0.10, "pyr_k": 0.0, "pyr_cap": 1.0, "give_back": 0.0},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01

# The SHORT whitelist: the inflation-crisis short-bond leg only (identical to keystone_shortmute).
_BORROWABLE = frozenset({"IDTL", "TLT", "SPTL", "EDV"})


# %% parameter space
def param_space():
    """Champion + ramp pinned at the killed grid's BEST convex cell; ``give_back`` is the swept lever.

    The v1.0.0 grid established the dose that maximizes convexity: ``pyr_k = 0.25`` gave the highest
    held-out convexity (0.9658) AND the highest return, and also the worst survivability (worst-split
    maxDD 1.94x the champion). This re-entry PINS that cell (``pyr_k = 0.25``, ``pyr_cap = 2.0`` the
    mandate ceiling) and sweeps only ``give_back`` - the vol-unit retracement-from-peak at which the
    added tranche is stopped back to champion size - to trace whether the stop BENDS the dd/convexity
    frontier or merely slides down it. ``give_back = 0`` disables the stop -> the v1.0.0 levered
    pyramid EXACTLY at pyr_k 0.25 (the in-grid killed-dose upper anchor, expected ~0.966 convexity /
    ~19.8% worst maxDD); active cells stop progressively tighter. The champion (pyr_k 0, maxDD 10.18%,
    Sharpe 1.15) is the survivability reference, cited as a constant from [[2026-07-06]] - not re-run,
    since a pyr_k=0 cell makes give_back inert and would just feed duplicate champion cells to the
    ranker. Only ``give_back`` is multi-valued: a single swept axis keeps mu-noise off the ranker.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "enter_band": vbt.Param([0.10]),
        "exit_band": vbt.Param([0.05]),
        "short_cap": vbt.Param([0.10]),
        "pyr_k": vbt.Param([0.25]),  # pinned: the killed grid's best-convexity cell
        "pyr_cap": vbt.Param([2.0]),  # mandate ceiling, pinned (never swept)
        "give_back": vbt.Param([0.0, 0.10, 0.15, 0.25]),  # 0.0 = stop off (killed-dose control)
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


def _pyramid_add(state_2d, logclose_2d, vol_2d, pyr_k, pyr_cap, give_back):
    """Per-name [1, pyr_cap] multiplier ADDING with the leg's vol-normalized favorable EXTENSION,
    with an optional high-water-mark give-back stop on the added tranche.

    A "leg" is a maximal run of constant latched state; its entry anchor is the log price at the
    bar the state took its current non-flat value (reset on a sign flip). The favorable extension
    since entry is ``ext = state * (logP - logP_anchor)`` and its vol-normalized form
    ``r = max(ext, 0) / annualized_vol`` drives ``m = 1 + (pyr_cap - 1) * clip(r / pyr_k, 0, 1)``:
    the champion weight on a fresh trade, ``pyr_cap`` x once the move has extended ``pyr_k``
    vol-units. ``pyr_k <= 0`` disables the ramp (all ones, the nested champion).

    ``give_back > 0`` arms a trailing stop on the tranche: each leg tracks its PEAK favorable
    extension, and once ``ext`` retraces ``give_back`` vol-units below that peak (``ext_peak - ext
    >= give_back * vol``) the multiplier LATCHES to 1 (the pyramid is unwound to champion size) for
    the rest of the leg, until a sign flip resets it. It arms only after the leg has actually
    pyramided (``ext_peak > 0``), so an early adverse wobble on a fresh leg does not pre-empt it.
    ``give_back <= 0`` leaves the ramp to unwind linearly with ``ext`` - the v1.0.0 behavior.
    """

    if pyr_k <= 0.0 or pyr_cap <= 1.0:
        return np.ones_like(logclose_2d)

    T, n = logclose_2d.shape
    vol = np.maximum(vol_2d, _MIN_VOL)
    mult = np.ones((T, n))
    anchor = logclose_2d[0].copy()
    ext_peak = np.zeros(n)  # per-leg high-water mark of favorable extension (log units)
    stopped = np.zeros(n, dtype=bool)  # tranche unwound for the rest of the current leg
    prev = np.zeros(n)
    use_stop = give_back > 0.0
    for t in range(T):
        s = state_2d[t]
        new_leg = (s != 0.0) & (s != prev)  # a new non-flat leg began this bar -> reset the anchor
        anchor = np.where(new_leg, logclose_2d[t], anchor)
        ext = np.where(s != 0.0, s * (logclose_2d[t] - anchor), 0.0)  # favorable move since entry
        r = np.maximum(ext, 0.0) / vol[t]  # vol-normalized extension, >= 0
        m = 1.0 + (pyr_cap - 1.0) * np.clip(r / pyr_k, 0.0, 1.0)
        if use_stop:
            ext_peak = np.where(new_leg, 0.0, ext_peak)  # reset the high-water mark on a new leg
            stopped = np.where(new_leg, False, stopped)  # re-arm the tranche on a new leg
            ext_peak = np.maximum(ext_peak, ext)  # update the high-water mark
            triggered = (ext_peak > 0.0) & ((ext_peak - ext) >= give_back * vol[t])
            stopped = stopped | (triggered & (s != 0.0))  # latch for the remainder of the leg
            m = np.where(stopped, 1.0, m)  # tranche unwound to champion size
        mult[t] = np.where(s != 0.0, m, 1.0)
        prev = s
    return mult


def _candidate_weights(
    score_2d, vol_2d, logclose_2d, enter_band, exit_band, short_cap, pyr_k, pyr_cap, give_back,
    shortable_row,
):
    """Champion shortmute FORGO weights, each trend leg's magnitude MULTIPLIED by its add ramp.

    The gross divisor is the champion's (from the UNCAPPED, FULL-SIZE signed book), so at m = 1
    the book is byte-identical to keystone_shortmute and at full extension a leg carries
    ``pyr_cap`` x its champion weight - the added gross is financed (margin-priced) rather than
    taken from the other legs.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    state = _hysteretic_state(score_2d, enter_band, exit_band)

    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / vol
    short_full = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / vol
    gross = np.abs(long_leg - short_full).sum(axis=1, keepdims=True)  # champion gross divisor

    short_muted = np.where(state < 0.0, np.minimum(np.maximum(-score, 0.0), short_cap), 0.0) / vol
    signed = long_leg - short_muted  # champion signed book (one-sided short_cap)

    mult = _pyramid_add(state, logclose_2d, vol_2d, pyr_k, pyr_cap, give_back)  # [1, pyr_cap] per leg
    signed = signed * mult  # add financed exposure to extended winners; entries stay champion-size

    kept = np.where(signed >= 0.0, signed, np.where(shortable_row, signed, 0.0))
    return kept / np.where(gross > 0.0, gross, 1.0)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized hysteretic L/S straddle (borrow-gated short, one-sided short cap) with a levered
    extension-driven pyramiding multiplier on every trend leg."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    shortable_row = np.array([[_base_symbol(c) in _BORROWABLE for c in close.columns]], dtype=bool)
    logclose = np.log(close.to_numpy().astype(np.float64))

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    enter_bands = param_lists["enter_band"]
    exit_bands = param_lists["exit_band"]
    short_caps = param_lists["short_cap"]
    pyr_ks = param_lists["pyr_k"]
    pyr_caps = param_lists.get("pyr_cap", [1.0] * n_candidates)
    give_backs = param_lists.get("give_back", [0.0] * n_candidates)

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        result_3d[:, ci, :] = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :], logclose,
            float(enter_bands[ci]), float(exit_bands[ci]), float(short_caps[ci]),
            float(pyr_ks[ci]), float(pyr_caps[ci]), float(give_backs[ci]), shortable_row,
        )

    return result_3d.reshape(T, n_candidates * n_symbols)
