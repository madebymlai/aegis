"""Independent market-anchored downside estimates for broken cash mergers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np


class BreakValueInputs(Protocol):
    @property
    def preannouncement_close(self) -> float: ...

    @property
    def preannouncement_closes(self) -> tuple[float, ...]: ...

    @property
    def market_close(self) -> float: ...

    @property
    def announcement_market_close(self) -> float: ...

    @property
    def beta(self) -> float: ...


@dataclass(frozen=True)
class BreakValueEstimate:
    """A bounded standalone-value estimate if the transaction breaks."""

    lower: float
    central: float
    upper: float


class BreakValueModel:
    """Market-adjust a robust range of pre-announcement standalone prices."""

    def estimate(self, inputs: BreakValueInputs) -> BreakValueEstimate:
        anchors = inputs.preannouncement_closes or (inputs.preannouncement_close,)
        market_scale = math.exp(
            inputs.beta
            * math.log(inputs.market_close / inputs.announcement_market_close)
        )
        lower, central, upper = np.quantile(
            np.asarray(anchors, dtype=float),
            (0.25, 0.50, 0.75),
        )
        return BreakValueEstimate(
            lower=round(float(lower) * market_scale, 10),
            central=round(float(central) * market_scale, 10),
            upper=round(float(upper) * market_scale, 10),
        )
