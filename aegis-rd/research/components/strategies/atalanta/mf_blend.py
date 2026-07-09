# %% component overview
# Atalanta MF-BLEND - the HYBRID arm of the trend-seat build-vs-buy test (GH #80, block 2,
# pre-registered as `dbmf_atalanta_blend` in [[runs/atalanta/2026-07-09]]).
#
# Blends the "buy" and "build" poles inside one trend sleeve:
#     target = w * (managed-futures wrapper long) + (1 - w) * (atalanta keystone_shortmute on core)
# where the convex core is the atalanta legs (IDTL/IGLN/ICOM) and every OTHER instrument is a
# bought-beta wrapper leg (the WTMF proxy). Nested controls make the endpoints exact:
#   w = 0 -> pure keystone_shortmute on the core -> reproduces the CHAMPION (trend_convexity 0.4451)
#   w = 1 -> pure wrapper long -> reproduces `atalanta.hold_wrapper`
# on the evaluated windows (the two collapse to identical books once the vol/trend warmup is past).
#
# The PARETO question ([[runs/atalanta/2026-07-09]]): is there an interior w that HOLDS the convexity
# floor (atalanta supplies the slow-crisis convexity the diversified wrapper dilutes) while the
# wrapper's breadth LIFTS standalone Sharpe? If convexity falls monotonically in w with no bulge,
# the poles are substitutes; if an interior w clears both, they are complements and the seat becomes
# wrapper-core + thin-atalanta-dose. The keystone half is byte-identical to the champion's FORGO
# weights (one-sided short cap, borrow-gated IDTL short); only its gross scaling by (1 - w) is new.

# %% imports
import numpy as np
import pandas as pd

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.mf_blend",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["blend_w", "enter_band", "exit_band", "short_cap"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"blend_w": 0.5, "enter_band": 0.10, "exit_band": 0.05, "short_cap": 0.10},
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (matches keystone).
_MIN_VOL = 0.01

# The convex core: the atalanta legs. Every column NOT in this set is a bought-beta wrapper leg.
_CONVEX_CORE = frozenset({"IDTL", "IGLN", "ICOM"})

# The SHORT whitelist: the inflation-crisis short-bond leg only (identical to keystone_shortmute).
_BORROWABLE = frozenset({"IDTL", "TLT", "SPTL", "EDV"})


# %% helpers
def _base_symbol(col):
    """Strip venue/currency suffix: 'IDTL.LSEETF' -> 'IDTL'."""
    return str(col).upper().split(".")[0].strip()


def _hysteretic_state(score_2d, enter_band, exit_band):
    """Schmitt-trigger sign latch per symbol (identical to keystone): +1 up, -1 down, prior state
    held in the dead-zone; NaN warmup and pre-first-breach rows read as flat (0)."""

    signal = np.where(score_2d > enter_band, 1.0, np.where(score_2d < -exit_band, -1.0, np.nan))
    state = pd.DataFrame(signal).ffill().to_numpy()
    return np.where(np.isfinite(state), state, 0.0)


def _keystone_core_weights(score_2d, vol_2d, enter_band, exit_band, short_cap, core_mask, shortable_row):
    """The champion keystone_shortmute FORGO weights, restricted to the convex-core columns.

    Byte-identical to the champion on the core legs: hysteretic sign, continuous magnitude / vol,
    one-sided short cap on the borrow-gated IDTL short, gross-normalized by the UNCAPPED signed
    book. Wrapper columns are masked out of the state so they contribute neither exposure nor gross.
    """

    vol = np.maximum(vol_2d, _MIN_VOL)
    score = np.where(np.isfinite(score_2d), score_2d, 0.0)
    state = _hysteretic_state(score_2d, enter_band, exit_band)
    state = np.where(core_mask, state, 0.0)  # only the convex core trades the keystone signal

    long_leg = np.where(state > 0.0, np.maximum(score, 0.0), 0.0) / vol
    short_full = np.where(state < 0.0, np.maximum(-score, 0.0), 0.0) / vol
    gross = np.abs(long_leg - short_full).sum(axis=1, keepdims=True)  # champion gross divisor

    short_muted = np.where(state < 0.0, np.minimum(np.maximum(-score, 0.0), short_cap), 0.0) / vol
    signed = long_leg - short_muted  # one-sided short_cap

    kept = np.where(signed >= 0.0, signed, np.where(shortable_row, signed, 0.0))
    return kept / np.where(gross > 0.0, gross, 1.0)


def _wrapper_weights(vol_2d, wrapper_mask):
    """Inverse-vol long of the wrapper leg(s), gross-normalized among themselves (a constant
    full-size long for a single wrapper proxy) - identical basis to ``atalanta.hold_wrapper``."""

    vol = np.maximum(vol_2d, _MIN_VOL)
    inv_vol = np.where(wrapper_mask, 1.0 / vol, 0.0)
    gross = inv_vol.sum(axis=1, keepdims=True)
    return np.where(gross > 0.0, inv_vol / gross, 0.0)


# %% parameter space
def param_space():
    """Sweep the blend weight ``w`` over the 5-point grid with the champion keystone params pinned.

    ``blend_w`` 0.0 and 1.0 are the nested controls (champion / hold_wrapper); the interior cells
    trace the convexity-vs-Sharpe frontier. Only ``blend_w`` is multi-valued so mu-noise stays off
    the ranker.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "blend_w": vbt.Param([0.0, 0.25, 0.50, 0.75, 1.0]),
        "enter_band": vbt.Param([0.10]),
        "exit_band": vbt.Param([0.05]),
        "short_cap": vbt.Param([0.10]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators' own."""
    return 0


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Convex-core keystone book scaled by (1 - w), plus the wrapper long scaled by w."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    base = [_base_symbol(c) for c in close.columns]
    core_mask = np.array([[b in _CONVEX_CORE for b in base]], dtype=bool)  # (1, n_symbols)
    wrapper_mask = ~core_mask
    shortable_row = np.array([[b in _BORROWABLE for b in base]], dtype=bool)

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    ws = param_lists["blend_w"]
    ebs = param_lists["enter_band"]
    xbs = param_lists["exit_band"]
    scs = param_lists["short_cap"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        w = float(ws[ci])
        core = _keystone_core_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :],
            float(ebs[ci]), float(xbs[ci]), float(scs[ci]), core_mask, shortable_row,
        )
        wrap = _wrapper_weights(vol_3d[:, ci, :], wrapper_mask)
        result_3d[:, ci, :] = (1.0 - w) * core + w * wrap

    return result_3d.reshape(T, n_candidates * n_symbols)
