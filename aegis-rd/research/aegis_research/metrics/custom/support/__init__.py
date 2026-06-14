"""Shared reads behind the custom Metrics.

Support modules that several custom Metric readers derive from. They hold no
registry records of their own — only the one-read-per-batch primitives a reader
constructs and asks.
"""

from research.aegis_research.metrics.custom.support.equity_curve import EquityCurve

__all__ = ["EquityCurve"]
