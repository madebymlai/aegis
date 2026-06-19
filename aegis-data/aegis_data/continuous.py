"""Back-adjusted continuous-futures series (Panama-canal method).

Stitches a chronological chain of dated futures contracts into one gap-free
continuous series so a deep-lookback signal is not corrupted at rolls.  The
most-recent contract is held unadjusted; historical contracts are scaled
(``ratio``) or shifted (``difference``) by the cumulative roll adjustment so the
seams are continuous and within-contract returns are preserved.

Pure: no I/O, no Nautilus, no provider.  Both Aegis RD (research data prep) and
Aegis Trader (live cross-roll stitching) reuse this transform.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def roll_adjustment_factors(
    contracts: Sequence[pd.Series],
    roll_dates: Sequence[pd.Timestamp],
    *,
    method: str = "ratio",
) -> tuple[float, ...]:
    """Per-contract cumulative roll adjustment, newest contract unadjusted.

    ``ratio`` returns multiplicative factors (newest = 1.0); ``difference``
    returns additive offsets (newest = 0.0).  Computed backward from each seam's
    gap between the two contracts at the roll date.  Exposed so a caller can
    apply ONE Close-derived adjustment consistently across O/H/L/C panels.

    *contracts* are chronological (oldest→newest), each indexed by date;
    consecutive contracts must overlap on their roll date.  *roll_dates* has one
    entry per seam (``len(contracts) - 1``).
    """
    n = len(contracts)
    if n == 0:
        raise ValueError("back_adjust requires at least one contract")
    if len(roll_dates) != n - 1:
        raise ValueError(
            f"expected {n - 1} roll date(s) for {n} contracts; got {len(roll_dates)}"
        )
    for i, roll in enumerate(roll_dates):
        if roll not in contracts[i].index or roll not in contracts[i + 1].index:
            raise ValueError(
                f"roll date {roll} is missing from the overlap of contracts {i} and "
                f"{i + 1}; back-adjustment needs the roll-day price in both contracts"
            )
    if method not in ("ratio", "difference"):
        raise ValueError(f"unknown back-adjust method {method!r}; expected 'ratio' or 'difference'")

    identity = 1.0 if method == "ratio" else 0.0
    adjustments = [identity] * n
    for i in range(n - 2, -1, -1):
        roll = roll_dates[i]
        old_price = contracts[i].loc[roll]
        new_price = contracts[i + 1].loc[roll]
        if method == "ratio":
            adjustments[i] = adjustments[i + 1] * (new_price / old_price)
        else:
            adjustments[i] = adjustments[i + 1] + (new_price - old_price)
    return tuple(adjustments)


def back_adjust(
    contracts: Sequence[pd.Series],
    roll_dates: Sequence[pd.Timestamp],
    *,
    method: str = "ratio",
) -> pd.Series:
    """Stitch dated-contract series into one back-adjusted continuous series.

    *contracts* are chronological (oldest→newest), each indexed by date;
    consecutive contracts must overlap on their roll date.  *roll_dates* has one
    entry per seam: ``roll_dates[i]`` is the date the series switches from
    ``contracts[i]`` to ``contracts[i + 1]`` (the new contract is active from
    that date, inclusive).
    """
    factors = roll_adjustment_factors(contracts, roll_dates, method=method)
    return apply_adjustment_factors(contracts, roll_dates, factors, method=method)


def apply_adjustment_factors(
    contracts: Sequence[pd.Series],
    roll_dates: Sequence[pd.Timestamp],
    factors: Sequence[float],
    *,
    method: str = "ratio",
) -> pd.Series:
    """Stitch each contract's active span, applying its precomputed *factor*.

    Active span: ``contracts[i]`` covers ``roll_dates[i-1] <= date < roll_dates[i]``
    (open-ended at the chain's ends).  Applying Close-derived factors here lets
    O/H/L/C share one adjustment.
    """
    n = len(contracts)
    pieces: list[pd.Series] = []
    for i, contract in enumerate(contracts):
        span = contract
        if i > 0:
            span = span[span.index >= roll_dates[i - 1]]
        if i < n - 1:
            span = span[span.index < roll_dates[i]]
        pieces.append(span * factors[i] if method == "ratio" else span + factors[i])
    return pd.concat(pieces).sort_index()


__all__ = ["apply_adjustment_factors", "back_adjust", "roll_adjustment_factors"]
