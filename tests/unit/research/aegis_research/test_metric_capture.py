"""Math tests for the benchmark-capture crash-gain Metrics.

The capture extractors are the only custom metrics that read beyond the value
curve (the batch's own SPY close per group), so their column surgery and
masking get a direct test against hand-computed captures.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.custom.capture import (
    CAPTURE_SPREAD_EXTRACTOR,
    NEG_DOWN_CAPTURE_EXTRACTOR,
)


class _StubPortfolio:
    def __init__(self, value: pd.DataFrame, close: pd.DataFrame) -> None:
        self._value = value
        self.close = close

    def get_value(self) -> pd.DataFrame:
        return self._value


def _stub_portfolio() -> _StubPortfolio:
    """Two groups over five bars: a SPY mirror and a crisis gainer.

    SPY path: -2%, +1%, -3%, +2%. Group "mirror" tracks it exactly; group
    "gainer" moves opposite on SPY-down days and flat on SPY-up days, so its
    down-capture is negative and its up-capture is zero.
    """
    index = pd.date_range("2022-01-03", periods=5, freq="B")
    spy = pd.Series([100.0, 98.0, 98.98, 96.0106, 97.930812], index=index)

    mirror = spy / spy.iloc[0] * 10_000.0
    gainer_returns = [np.nan, 0.02, 0.0, 0.03, 0.0]
    gainer = pd.Series(
        10_000.0 * pd.Series(gainer_returns, index=index).fillna(0.0).add(1.0).cumprod(),
        index=index,
    )

    groups = pd.Index(["mirror", "gainer"], name="candidate_id")
    value = pd.DataFrame({"mirror": mirror, "gainer": gainer})
    value.columns = groups

    close_columns = pd.MultiIndex.from_product(
        [groups, ["SPY", "TLT"]], names=["candidate_id", SYMBOL_LEVEL]
    )
    close = pd.DataFrame(
        {
            column: (spy if column[1] == "SPY" else pd.Series(50.0, index=index))
            for column in close_columns
        }
    )
    close.columns = close_columns
    return _StubPortfolio(value, close)


def test_neg_down_capture_signs_mirror_and_gainer() -> None:
    pf = _stub_portfolio()
    result = NEG_DOWN_CAPTURE_EXTRACTOR.read(pf, ReportConfig())

    # The mirror compounds exactly the benchmark's down days: capture 1, negated -1.
    assert result["mirror"] == pytest.approx(-1.0)
    # The gainer makes +2% and +3% on the two SPY-down days:
    # (1.02 * 1.03 - 1) / (0.98 * (1 - 0.03) - 1) = 0.0506 / -0.0494 < 0 -> negated > 0.
    expected = -((1.02 * 1.03 - 1.0) / (0.98 * 0.97 - 1.0))
    assert result["gainer"] == pytest.approx(expected)


def test_capture_spread_rewards_asymmetry() -> None:
    pf = _stub_portfolio()
    result = CAPTURE_SPREAD_EXTRACTOR.read(pf, ReportConfig())

    # The mirror captures both sides fully: spread 0.
    assert result["mirror"] == pytest.approx(0.0)
    # The gainer: up-capture 0 (flat on SPY-up days), down-capture negative.
    expected = 0.0 - ((1.02 * 1.03 - 1.0) / (0.98 * 0.97 - 1.0))
    assert result["gainer"] == pytest.approx(expected)
