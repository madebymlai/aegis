# %% component overview
# Atalanta DONCHIAN-STATE trend signal - a sticky, hysteretic breakout latch, drop-in for
# atalanta.trend_score (same output name "trend_score"). Where the score variants emit a
# continuous annualized momentum, this emits a SIGNED DISCRETE STATE per symbol: +1 once Close
# breaks above its prior entry_window high (up-breakout), -1 once Close breaks below its prior
# exit_window low (down-breakout), and the PRIOR state is carried through the dead-zone between.
# With entry_window > exit_window the gap between the two channels IS the dead-zone, so near-zero
# noise no longer flips the sign - the dominant whipsaw cost under a fixed per-order fee. Donchian
# breakout is the low-turnover base layer many CTAs still run, parameter-insensitive and
# structurally hysteretic (bounded losses in chop, rides the breakout).
#
# WHY SIGNED (-1), not long/flat {0,+1}: the consuming FORGO strategy takes its gross from the
# UNCLIPPED signed book and then drops shorts to CASH. A down-state of -1 keeps that name in the
# pre-clip gross so its budget becomes cash (the validated cash-when-flat de-risk that halves the
# tail drawdown); a {0,+1} state would instead re-lever the survivors to gross 1 and destroy it.
# So the invested fraction here is the inverse-vol-weighted BREADTH of uptrends: 0 names up -> all
# cash, all names up -> fully invested. Magnitude-of-trend conviction is deliberately discarded
# (the point of a discrete sticky state); cross-name sizing comes from realized_vol downstream.
#
# WHY entry_window > exit_window: slow to enter (a long N-bar high), fast to exit (a near M-bar
# low) is the convex cut-fast/add-slow trend shape - here expressed in SIGNAL space, where it is
# live-research-parity safe (the live path recomputes this same causal latch and reads its latest
# value), unlike an asymmetry placed on the trade/execution step which the live rebalancer ignores.
# Still ABSOLUTE/time-series momentum (price vs its OWN past extremes) and still de-risks in
# downtrends (state -> -1 -> dropped to cash), so the lookback-straddle convexity is preserved.
# Entry windows span the slow convex band (~6-12mo) where trend convexity lives at the quarterly
# measurement horizon ([[what-makes-a-trend-sleeve-convex]]).

# %% imports
import numpy as np
import pandas as pd
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.donchian_state",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["entry_window", "exit_window"],
    "output_names": ["trend_score"],
    "defaults": {"entry_window": 189, "exit_window": 42},
}


# %% parameter space
def param_space():
    """VBT-native Donchian channels: a SLOW entry channel and a faster exit channel.

    Every entry window (>=126) exceeds every exit window (<=63), so the dead-zone (cut-fast /
    add-slow) holds across the whole grid. The entry band stays in the slow convex zone; the
    exit band is shorter so a downtrend de-risks to cash quickly.
    """

    return {
        "entry_window": vbt.Param([126, 189, 252]),
        "exit_window": vbt.Param([21, 42, 63]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars: the entry channel needs entry_window prior closes before it is defined."""
    return int(params["entry_window"])


# %% helpers
def _donchian_state(close, entry_window, exit_window):
    """Signed, hysteretic Donchian breakout latch per symbol: +1 up-state, -1 down-state.

    The channels are built from STRICTLY PAST closes (rolling max/min then shift(1)), so the
    breakout test at bar t never reads bar t - no look-ahead. Between breakouts the latch carries
    the prior state forward (the dead-zone hold). Computed on the full series so the channel warmup
    is incurred once, not per split window (the windowed-compute-in-indicator rule).
    """

    prior_high = close.rolling(entry_window).max().shift(1)  # highest of the prior entry_window closes
    prior_low = close.rolling(exit_window).min().shift(1)  # lowest of the prior exit_window closes
    up_break = (close > prior_high).to_numpy()  # a new entry_window-bar high
    down_break = (close < prior_low).to_numpy()  # a new exit_window-bar low

    # Down-break takes precedence (de-risk priority); the two are mutually exclusive in practice
    # (a close cannot be both above the long-window high and below the short-window low).
    signal = np.where(down_break, -1.0, np.where(up_break, 1.0, np.nan))
    # Forward-fill the latch: carry the last breakout state through the dead-zone. Leading rows
    # before the first breakout stay NaN (no state yet); the strategy reads NaN as flat.
    state = pd.DataFrame(signal, index=close.index, columns=close.columns).ffill().to_numpy()

    # Rows before a full entry channel are warmup -> NaN so the strategy excludes them rather than
    # acting on an exit-only signal (matches atalanta.trend_score's lookback-warmup convention).
    state[:entry_window] = np.nan
    return state


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta Donchian-state trend signal for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    entry_windows = param_lists["entry_window"]
    exit_windows = param_lists["exit_window"]

    result = np.full((T, n_candidates * n_symbols), np.nan)
    computed = {}
    for ci in range(n_candidates):
        key = (int(entry_windows[ci]), int(exit_windows[ci]))
        if key not in computed:
            computed[key] = _donchian_state(close, key[0], key[1])
        result[:, ci * n_symbols : (ci + 1) * n_symbols] = computed[key]

    return {"trend_score": result}
