from __future__ import annotations

import pandas as pd

from research.aegis_research.market_data import features, loading, native_metadata, panels


def test_market_data_panel_and_metadata_helpers_live_in_leaf_modules() -> None:
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
    assert callable(native_metadata.native_data_metadata)
