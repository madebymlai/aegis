"""Canonical materialised Array container."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MarketDataBundle:
    """Eager value object of materialised Array panels.

    Dict membership is the sole guard — an array is loaded iff it is a key.
    """

    arrays: Mapping[str, pd.DataFrame]

    def array(self, name: str) -> pd.DataFrame:
        try:
            return self.arrays[name]
        except KeyError:
            raise ValueError(f"market data array {name!r} was not supplied") from None
