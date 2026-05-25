from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.configuration.schema import ReportConfig
from research.aegis_research.metrics.accessors import central_metrics_from_accessors
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.optimization.runner import METRIC_INDEX_NAME


def _build_portfolio() -> Any:
    """Build a minimal VBT portfolio with known trades for testing."""
    index = pd.date_range("2024-01-01", periods=30, freq="D")
    close = pd.DataFrame(
        {"A": 100 + np.cumsum(np.random.default_rng(42).normal(0, 1, 30))},
        index=index,
    )
    entries = pd.DataFrame({"A": False}, index=index)
    exits = pd.DataFrame({"A": False}, index=index)
    entries.iloc[0] = True
    exits.iloc[5] = True
    entries.iloc[10] = True
    exits.iloc[15] = True
    entries.iloc[20] = True
    exits.iloc[25] = True
    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        fees=0.001,
        init_cash=10_000,
    )
    return pf


def test_returns_series_with_all_central_metric_keys() -> None:
    pf = _build_portfolio()
    config = ReportConfig()

    result = central_metrics_from_accessors(pf, config)

    assert isinstance(result, pd.Series)
    assert result.name == "value"
    assert result.index.name == METRIC_INDEX_NAME
    assert set(result.index) == set(PORTFOLIO_METRIC_VALUE_KEYS)


def test_parity_with_report_grade_path_for_finite_portfolio() -> None:
    from research.aegis_research.reports import portfolio_metrics

    pf = _build_portfolio()
    config = ReportConfig()

    lightweight = central_metrics_from_accessors(pf, config)
    report = portfolio_metrics(pf, config)

    for metric_name in PORTFOLIO_METRIC_VALUE_KEYS:
        report_value = report[metric_name]
        lightweight_value = lightweight[metric_name]
        if report_value is None:
            assert lightweight_value is None, f"{metric_name}: expected None, got {lightweight_value}"
        else:
            assert lightweight_value == pytest.approx(report_value, rel=1e-6), (
                f"{metric_name}: lightweight={lightweight_value} vs report={report_value}"
            )


def test_non_finite_values_normalize_to_none() -> None:
    index = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.DataFrame({"A": [100.0] * 10}, index=index)
    pf = vbt.Portfolio.from_signals(
        close,
        entries=pd.DataFrame({"A": [False] * 10}, index=index),
        exits=pd.DataFrame({"A": [False] * 10}, index=index),
        fees=0.0,
        init_cash=10_000,
    )
    config = ReportConfig()

    result = central_metrics_from_accessors(pf, config)

    assert result["total_return"] == pytest.approx(0.0)
    assert result["max_dd"] == pytest.approx(0.0)
    assert result["total_trades"] == pytest.approx(0.0)
    assert pd.isna(result["win_rate"]), "win_rate should be NaN when no trades"
    assert result["total_fees_paid"] == pytest.approx(0.0)
    assert pd.isna(result["sharpe_ratio"]), "sharpe_ratio should be NaN for flat returns"
