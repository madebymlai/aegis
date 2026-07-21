"""Bounds-aware native and canonical-primitives Metric extractors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from research.aegis_research.configuration import ReportConfig


@dataclass(frozen=True)
class FullPathPrimitives:
    """Canonical full-path inputs for custom bounds-aware Metrics."""

    value: pd.DataFrame
    close: pd.DataFrame
    canonical_returns: pd.DataFrame
    sim_start: int | None = None
    sim_end: int | None = None

    @classmethod
    def from_portfolio(cls, portfolio: Any) -> FullPathPrimitives:
        value = portfolio.get_value()
        if isinstance(value, pd.Series):
            value = value.to_frame()
        returns = portfolio.get_returns(rec_sim_range=False)
        if isinstance(returns, pd.Series):
            returns = returns.to_frame()
        return cls(value=value, close=portfolio.close, canonical_returns=returns)

    def for_bounds(self, sim_start: int, sim_end: int) -> FullPathPrimitives:
        return replace(self, sim_start=sim_start, sim_end=sim_end)

    def get_value(self) -> pd.DataFrame:
        return self.value


def custom_range_factory(read: Callable[..., Any]) -> Callable[[ReportConfig], Callable[..., Any]]:
    """Adapt a custom full-path reader to the exact bounds extractor interface."""

    def factory(config: ReportConfig) -> Callable[..., Any]:
        def extractor(
            primitives: FullPathPrimitives, *, sim_start: int, sim_end: int
        ) -> Any:
            return read(primitives.for_bounds(sim_start, sim_end), config)

        return extractor

    return factory


__all__ = ["FullPathPrimitives", "custom_range_factory"]
