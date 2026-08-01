"""The one input value passed to every Strategy Component."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from aegis_runtime.domain.market_data import MarketDataBundle


@dataclass(frozen=True)
class ComponentStrategyInputs:
    data: MarketDataBundle
    indicators: Mapping[str, np.ndarray]
    n_candidates: int
    n_symbols: int
    metadata: dict[str, Any]
