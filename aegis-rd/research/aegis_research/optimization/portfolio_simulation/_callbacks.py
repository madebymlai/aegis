"""Stable callback exports for VBT staticization."""

from research.aegis_research.optimization.portfolio_simulation._simulation import (
    _band_pre_order_segment_nb as pre_order_segment_func_nb,
)

__all__ = ["pre_order_segment_func_nb"]
