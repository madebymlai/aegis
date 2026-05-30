from __future__ import annotations

import pandas as pd
import pytest

from research.aegis_research.market_data import features, loading, panels, safety


def test_market_data_panel_and_safety_helpers_live_in_leaf_modules() -> None:
    frame = pd.DataFrame(
        {
            ("AAA", "Close"): [1.0, 2.0],
            ("BBB", "Close"): [3.0, 4.0],
        },
        index=pd.date_range("2020-01-01", periods=2, tz="UTC"),
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=["symbol", "feature"])

    close = features.feature_from_ohlcv(frame, "Close")

    assert list(close.columns) == ["AAA", "BBB"]
    assert panels.feature_from_frame(frame, "Close").equals(close)
    assert loading.feature_from_ohlcv is features.feature_from_ohlcv
    assert loading.assert_public_metadata_safe is safety.assert_public_metadata_safe
    with pytest.raises(ValueError, match="non-portable path"):
        safety.assert_public_metadata_safe({"source": "/home/alice/cache.db"})
