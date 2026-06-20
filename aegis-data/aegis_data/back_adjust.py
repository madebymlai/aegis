"""Back-adjust a contract chain into one continuous OHLCV panel.

Bridges :class:`aegis_data.chain.ContractChain` and the pure transform
(:mod:`aegis_data.continuous`): the roll factors are derived once from Close and
applied across all price arrays so each bar stays internally consistent; Volume
is stitched per active span without a price factor.
"""

from __future__ import annotations

import pandas as pd

from aegis_data.chain import ContractChain
from aegis_data.continuous import apply_adjustment_factors, roll_adjustment_factors

_PRICE_COLUMNS = frozenset({"Open", "High", "Low", "Close"})


def back_adjust_chain(chain: ContractChain, *, method: str = "ratio") -> pd.DataFrame:
    """Continuous OHLCV panel for one future, back-adjusted from its chain."""
    closes = [frame["Close"] for frame in chain.frames]
    price_factors = roll_adjustment_factors(closes, chain.roll_dates, method=method)
    identity = tuple(1.0 for _ in chain.frames)

    columns: dict[str, pd.Series] = {}
    for column in chain.frames[0].columns:
        series = [frame[column] for frame in chain.frames]
        if column in _PRICE_COLUMNS:
            columns[column] = apply_adjustment_factors(
                series, chain.roll_dates, price_factors, method=method
            )
        else:
            # Volume (and any non-price array): stitch active spans, no factor.
            columns[column] = apply_adjustment_factors(
                series, chain.roll_dates, identity, method="ratio"
            )
    return pd.DataFrame(columns)


__all__ = ["back_adjust_chain"]
