"""Seam-count rule: ``count_non_executable_rows`` is pure index geometry.

The rule owns the structural semantic of ``non_executable_rows``: the number
of window rows whose bar is not the immediate successor of the previous row's
bar in the market calendar — computable from the indexes alone, independent
of allocation values, candidates, or sweep chunking.
"""

from __future__ import annotations

import pandas as pd
import pytest

from research.aegis_research.portfolios import count_non_executable_rows


def test_gapped_window_counts_one_seam_row() -> None:
    market_index = pd.date_range("2024-01-01", periods=5)
    window_index = market_index[[0, 1, 3, 4]]

    assert count_non_executable_rows(window_index, market_index) == 1


def test_contiguous_window_counts_zero_seam_rows() -> None:
    market_index = pd.date_range("2024-01-01", periods=5)

    assert count_non_executable_rows(market_index[:4], market_index) == 0


def test_no_market_index_means_every_row_executable() -> None:
    window_index = pd.date_range("2024-01-01", periods=4)

    assert count_non_executable_rows(window_index, None) == 0


def test_market_index_missing_a_window_row_raises() -> None:
    window_index = pd.date_range("2024-01-01", periods=3)
    market_index = window_index[[0, 2]]

    with pytest.raises(ValueError, match="market_index"):
        count_non_executable_rows(window_index, market_index)
