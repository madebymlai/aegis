from __future__ import annotations

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from research.configs.demeter.cash_merger_evaluation import (
    summarize_cash_merger_execution,
)


def test_cash_merger_report_attributes_breaks_costs_concentration_and_execution() -> None:
    first = InstrumentId.from_str("FIRST.XNAS")
    second = InstrumentId.from_str("SECOND.XNAS")
    index = pd.date_range("2026-01-01", periods=3)
    close = pd.DataFrame({first: [100.0, 100.0, 70.0], second: [50.0, 51.0, 52.0]}, index=index)
    targets = pd.DataFrame({first: [0.10, 0.10, 0.0], second: [0.05, 0.05, 0.05]}, index=index)
    status = pd.DataFrame({first: [1.0, 1.0, -1.0], second: [1.0, 1.0, 1.0]}, index=index)
    assets = pd.DataFrame({first: [1.0, 1.0, 1.0], second: [0.0, 0.0, 0.0]}, index=index)
    value = pd.Series([1_000.0, 1_001.0, 972.0], index=index)

    report = summarize_cash_merger_execution(
        close=close,
        target_weights=targets,
        deal_status=status,
        assets=assets,
        portfolio_value=value,
        order_fees=1.40,
        size_increments={first: 1.0, second: 1.0},
    )

    assert report["concentration"]["maximum_target_weight"] == 0.10
    assert report["concentration"]["maximum_active_positions"] == 2
    assert report["deployment"]["mean_target_fraction"] == pytest.approx(
        (0.15 + 0.15 + 0.05) / 3.0
    )
    assert report["deployment"]["mean_realized_fraction"] == pytest.approx(
        (100.0 / 1_000.0 + 100.0 / 1_001.0 + 70.0 / 972.0) / 3.0
    )
    assert report["deployment"]["mean_unexpressed_target_fraction"] == pytest.approx(
        ((0.15 - 100.0 / 1_000.0) + (0.15 - 100.0 / 1_001.0)) / 3.0
    )
    assert report["costs"]["realized_order_fees"] == 1.40
    assert report["execution"]["fractional_execution_used"] is False
    assert report["resolution_attribution"]["terminated_contribution"] == pytest.approx(
        -30.0 / 1_001.0
    )
