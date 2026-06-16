# %% component overview
# Atalanta trend-straddle + turnover buffer + SHORT-EXECUTABILITY PROBE.
# Identical long book, signal, vol-sizing and no-trade band as atalanta.trendStraddleBuffered;
# the ONLY change is a per-symbol short gate `short_policy`:
#   "all"        - short any downtrending name (== trendStraddleBuffered, the live champion)
#   "none"       - long-only: drop every short leg (cash that budget; longs unchanged)
#   "borrowable" - short only names IBKR shows borrow inventory for (2026-06 paper probe);
#                  drop shorts on the rest, longs unchanged
# CRITICAL: gross is computed ONCE from the unclipped weights and reused, so the LONG legs
# are byte-identical across all three policies. Therefore:
#   P&L(all) - P&L(none)        == the entire short book's contribution
#   P&L(all) - P&L(borrowable)  == the UNBORROWABLE short legs' contribution
#   P&L(borrowable) - P&L(none) == the BORROWABLE short legs' contribution
# This answers "is shorting important for atalanta, and does the IBKR borrow gap cost edge?"
# Throwaway research probe — not a production strategy.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "atalanta.trendStraddleBufferedShortMask",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["entry_band", "buffer_band", "short_policy", "gross_fill"],
    "output_name": "target_weights",
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {
        "entry_band": 0.0,
        "buffer_band": 0.20,
        "short_policy": "all",
        "gross_fill": "forgo",
    },
    "owns_portfolio": False,
}

# Vol floor: below this annualized vol the inverse-vol weight is capped (see trendStraddle).
_MIN_VOL = 0.01

# Names IBKR returned borrow inventory for on the 2026-06-16 paper-account probe
# (DUQ455398, delayed feed). The other 10 trend names (AIGC AIGA SSLV WEAT HEAT COCO
# NGAS IGLO GILI GBUS) returned no borrow across all listings.
_BORROWABLE = frozenset(
    {"IDTL", "IBTA", "IGLN", "SEGA", "EMCP", "HYLD", "ITPS", "COPA", "BRNT", "IEGE"}
)


# %% parameter space
def param_space():
    """Entry dead-zone × no-trade band × short-execution policy."""

    return {
        "entry_band": vbt.Param([0.0, 0.05]),
        "buffer_band": vbt.Param([0.0, 0.10, 0.20, 0.30]),
        "short_policy": vbt.Param(["all", "none", "borrowable"]),
        # forgo: keep longs at baseline size, drop short budget to cash (gross <= 1).
        # redeploy: re-normalize to gross 1 (re-lever freed budget into longs) → gross-matched
        # to the L/S baseline so the comparison is not confounded by exposure.
        "gross_fill": vbt.Param(["forgo", "redeploy"]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the indicators'."""
    return 0


# %% helpers
def _base_symbol(col):
    """Strip venue/currency suffix: 'IDTL.L' -> 'IDTL'."""
    return str(col).upper().split(".")[0].strip()


def _candidate_weights(score_2d, vol_2d, entry_band, policy, borrowable_row, gross_fill):
    """Signed vol-scaled conviction weights, then the short gate.

    ``borrowable_row`` is a (1, n_symbols) bool mask. ``gross_fill`` controls re-leverage:
    ``forgo`` divides by the UNCLIPPED gross (longs held at baseline size, dropped shorts
    become cash → gross <= 1); ``redeploy`` divides by the post-clip gross (re-normalize to
    gross 1, re-levering the freed budget into the longs) so the book is gross-matched to the
    L/S baseline. For policy ``all`` the two are identical (nothing is clipped).
    """
    vol = np.maximum(vol_2d, _MIN_VOL)
    raw = np.where(np.abs(score_2d) > entry_band, score_2d / vol, 0.0)
    raw = np.where(np.isfinite(raw), raw, 0.0)
    pre_gross = np.abs(raw).sum(axis=1, keepdims=True)

    if policy == "none":
        raw = np.maximum(raw, 0.0)
    elif policy == "borrowable":
        blocked = (raw < 0.0) & (~borrowable_row)
        raw = np.where(blocked, 0.0, raw)
    elif policy != "all":
        raise ValueError(f"unknown short_policy {policy!r}")

    if gross_fill == "redeploy":
        divisor = np.abs(raw).sum(axis=1, keepdims=True)  # post-clip → gross 1
    elif gross_fill == "forgo":
        divisor = pre_gross  # longs unchanged; gross <= 1
    else:
        raise ValueError(f"unknown gross_fill {gross_fill!r}")

    return raw / np.where(divisor > 0, divisor, 1.0)


def _apply_buffer(weights, band):
    """No-trade band: carry the held book until L1 drift from the new target exceeds ``band``."""

    if band <= 0.0:
        return weights
    out = weights.copy()
    held = weights[0].copy()
    for t in range(1, len(weights)):
        if np.abs(weights[t] - held).sum() > band:
            held = weights[t].copy()
        out[t] = held
    return out


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Vectorized buffered long/short straddle with a per-symbol short-execution gate."""

    close = inputs.data.array("Close")
    n_symbols = inputs.n_symbols
    T = len(close)

    borrowable_row = np.array(
        [[_base_symbol(c) in _BORROWABLE for c in close.columns]], dtype=bool
    )

    score_3d = inputs.indicators["trend_score"].reshape(T, n_candidates, n_symbols)
    vol_3d = inputs.indicators["realized_vol"].reshape(T, n_candidates, n_symbols)
    entry_bands = param_lists["entry_band"]
    buffer_bands = param_lists["buffer_band"]
    policies = param_lists["short_policy"]
    gross_fills = param_lists["gross_fill"]

    result_3d = np.full((T, n_candidates, n_symbols), np.nan)
    for ci in range(n_candidates):
        w = _candidate_weights(
            score_3d[:, ci, :], vol_3d[:, ci, :],
            float(entry_bands[ci]), str(policies[ci]), borrowable_row, str(gross_fills[ci]),
        )
        result_3d[:, ci, :] = _apply_buffer(w, float(buffer_bands[ci]))

    return result_3d.reshape(T, n_candidates * n_symbols)
