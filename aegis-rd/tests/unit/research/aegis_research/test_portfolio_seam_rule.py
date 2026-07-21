"""Seam-count rule through the Window Evaluation query.

``non_executable_rows(window_index)`` answers the seam cost of one window: the
number of rows whose bar is not the immediate successor of the previous row's
bar in the market calendar the evaluator already owns — pure index geometry,
independent of allocation values, candidates, or sweep chunking. The caller
never supplies the calendar; the evaluator reads it off its own arrays.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.optimization.precompute import empty_precompute
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.optimization.window_evaluation import (
    ResolvedBook,
    WindowEvaluator,
)
from tests.support.research.aegis_research.factories import (
    make_portfolio_config,
    make_report_config,
    make_run_arrays,
)


def _never_simulate(*args: object, **kwargs: object) -> object:
    raise AssertionError("the geometry query must not simulate")


def _evaluator(market_index: pd.Index) -> WindowEvaluator:
    close = pd.DataFrame({"SYN": np.ones(len(market_index))}, index=market_index)
    return WindowEvaluator(
        source=OptimizationSource(
            precompute=empty_precompute,
            simulate=_never_simulate,
            resolve_lookbacks=lambda params: {"source": 0},
            params={"alpha": vbt.Param([1.0])},
            output_name="target_weights",
            evidence={},
            diagnostics={},
            metadata={},
        ),
        book=ResolvedBook(make_portfolio_config()),
        report=make_report_config(),
        arrays=make_run_arrays(close=close, open_=close),
        store=empty_precompute(close, 1, alpha=[1.0]),
        extractors={},
    )


def test_gapped_window_counts_one_seam_row() -> None:
    market_index = pd.date_range("2024-01-01", periods=5)

    assert _evaluator(market_index).non_executable_rows(market_index[[0, 1, 3, 4]]) == 1


def test_contiguous_window_counts_zero_seam_rows() -> None:
    market_index = pd.date_range("2024-01-01", periods=5)

    assert _evaluator(market_index).non_executable_rows(market_index[:4]) == 0


def test_market_calendar_missing_a_window_row_raises() -> None:
    window_index = pd.date_range("2024-01-01", periods=3)
    evaluator = _evaluator(window_index[[0, 2]])

    with pytest.raises(ValueError, match="market_index"):
        evaluator.non_executable_rows(window_index)
