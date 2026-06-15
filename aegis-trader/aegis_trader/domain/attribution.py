"""Per-sleeve P&L attribution — derived from weights × book returns.

Not a second ledger — one pure function that computes each sleeve's
contribution to book P&L using the identity:

    P&L_sleeve = Σ_t (w_{i,t-1} × ret_{i,t} × NAV_{t-1})

where ret_{i,t} = close_{i,t} / close_{i,t-1} - 1.

Sleeve attributions must sum to the total book P&L (the linearity of the
weighted-return decomposition guarantees this).  The function is a pure
domain component — no Nautilus, no I/O.
"""

from __future__ import annotations

import pandas as pd

from aegis_trader.domain.types import SleeveName


def compute_sleeve_attribution(
    *,
    sleeve_targets: dict[SleeveName, pd.DataFrame],
    closes: pd.DataFrame,
    nav_series: pd.Series,
) -> dict[SleeveName, float]:
    """Compute per-sleeve P&L as the cumulative sum of weight_{t-1} × return_t × NAV_{t-1}.

    *sleeve_targets* — maps each sleeve to its target-weight DataFrame
      (index=timestamp, columns=FIGI strings).  The weight at time t-1 is
      applied to the return from t-1 to t.
    *closes* — DataFrame of close prices (index=timestamp, columns=FIGI strings).
      Must contain the FIGIs that appear in the sleeve targets.
    *nav_series* — Series of NAV values at each timestamp (index matches closes).

    Returns a dict mapping each SleeveName to its cumulative P&L in base currency.
    An empty dict when no sleeves are supplied.

    Any FIGI present in sleeve_targets but missing from *closes* contributes zero
    — the function does not error on partial data.
    """
    if not sleeve_targets:
        return {}

    result: dict[SleeveName, float] = {}

    for sleeve_name, weights_df in sleeve_targets.items():
        if weights_df.empty:
            result[sleeve_name] = 0.0
            continue

        # Align closes and weights on common index
        common_idx = weights_df.index.intersection(closes.index)
        if len(common_idx) < 2:
            result[sleeve_name] = 0.0
            continue

        closes_aligned = closes.loc[common_idx]
        nav_aligned = nav_series.loc[common_idx]

        # Align weights — use the weight at time t-1 for return from t-1 to t
        weights_aligned = weights_df.loc[common_idx]

        pnl = 0.0
        prev_close = closes_aligned.iloc[0]
        prev_weight = weights_aligned.iloc[0]
        prev_nav = nav_aligned.iloc[0]

        for t in range(1, len(common_idx)):
            curr_close = closes_aligned.iloc[t]
            curr_weight = weights_aligned.iloc[t]
            curr_nav = nav_aligned.iloc[t]

            for figi in weights_df.columns:
                w = float(prev_weight.get(figi, 0.0))
                if abs(w) < 1e-15:
                    continue
                prev_px = prev_close.get(figi)
                curr_px = curr_close.get(figi)
                if prev_px is None or curr_px is None:
                    continue
                prev_px, curr_px = float(prev_px), float(curr_px)
                if pd.isna(prev_px) or pd.isna(curr_px) or prev_px <= 0:
                    continue
                ret = curr_px / prev_px - 1.0
                pnl += w * ret * prev_nav

            # Shift the window: current becomes previous for the next period.
            prev_close = curr_close
            prev_weight = curr_weight
            prev_nav = curr_nav

        result[sleeve_name] = pnl

    return result
