"""The one portfolio-value read behind every custom Metric.

A custom Metric reader honours the one-read-per-batch contract (ADR-0006) by
constructing one :class:`EquityCurve` and asking it — drawdown curve, annualized
return, daily returns, benchmark-aligned returns — rather than re-reading the
portfolio. The single ``get_value`` read and the ``SYMBOL_LEVEL`` benchmark
alignment live here, in one place, so the readers carry only their distinctive
statistic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL


@dataclass(frozen=True)
class EquityCurve:
    """The per-Candidate portfolio value frame from one ``get_value`` read.

    ``value`` is the portfolio value over time, one column per Candidate group; a
    Series (a one-group batch) is normalized to a frame on construction. ``close``
    is the batch's own input close panel, captured so benchmark-relative reads
    need no second portfolio read.
    """

    value: pd.DataFrame
    close: pd.DataFrame
    canonical_returns: pd.DataFrame | None = None
    sim_start: int | None = None
    sim_end: int | None = None

    @classmethod
    def from_portfolio(cls, pf: Any) -> EquityCurve:
        """Make the single ``pf.get_value()`` read and capture the close panel."""
        value = pf.get_value()
        if isinstance(value, pd.Series):
            value = value.to_frame()
        return cls(
            value=value,
            close=pf.close,
            canonical_returns=getattr(pf, "canonical_returns", None),
            sim_start=getattr(pf, "sim_start", None),
            sim_end=getattr(pf, "sim_end", None),
        )

    def drawdown_curve(self) -> pd.DataFrame:
        """Per-Candidate drawdown from the running peak: ``value / cummax - 1`` (<= 0)."""
        if self.canonical_returns is None:
            drawdown = self.value / self.value.cummax() - 1.0
        else:
            cumulative = (1.0 + self.canonical_returns.fillna(0.0)).cumprod()
            drawdown = cumulative / cumulative.cummax() - 1.0
        return self._range(drawdown)

    def annualized_return(self, periods_per_year: int) -> pd.Series:
        """Per-Candidate geometric annualized return over the window."""
        returns = self.returns()
        growth = (1.0 + returns.fillna(0.0)).prod()
        return growth ** (periods_per_year / len(returns)) - 1.0

    def returns(self) -> pd.DataFrame:
        """Per-Candidate daily simple returns of the value frame."""
        returns = (
            self.canonical_returns
            if self.canonical_returns is not None
            else self.value.pct_change(fill_method=None)
        )
        return self._range(returns)

    def has_symbol(self, symbol: str) -> bool:
        """Whether ``symbol`` is a traded column of the close panel."""
        return symbol in self.close.columns.get_level_values(SYMBOL_LEVEL)

    def benchmark_returns(self, symbol: str) -> pd.DataFrame:
        """Daily returns of ``symbol`` from the close panel, aligned per Candidate.

        The benchmark close is identical content across groups; its columns are
        relabelled to the value frame's Candidate columns so a (stream, benchmark)
        pairing lines up column-for-column.
        """
        benchmark_close = self.close.xs(symbol, level=SYMBOL_LEVEL, axis=1)
        benchmark_close.columns = self.value.columns
        return self._range(benchmark_close.pct_change(fill_method=None))

    def aligned_benchmark_returns(self, close: pd.Series) -> pd.DataFrame:
        """Returns of an externally-supplied benchmark close, aligned per Candidate.

        For a benchmark sourced outside the traded panel (see convexity's lazy pull):
        the close is reindexed to the value frame and broadcast to its Candidate columns,
        so the (stream, benchmark) pairing lines up exactly as for a traded benchmark.
        """
        aligned = close.reindex(self.value.index).ffill()
        broadcast = pd.DataFrame(
            {col: aligned.to_numpy() for col in self.value.columns},
            index=self.value.index,
        )
        return self._range(
            broadcast.pct_change(fill_method=None)
        )  # already ffilled; avoid redundant pad

    def _range(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self.sim_start is None and self.sim_end is None:
            return frame
        return frame.iloc[self.sim_start : self.sim_end]
