from __future__ import annotations

import pandas as pd

from research.aegis_research.market_data import features


def test_feature_accessors_live_in_features_module() -> None:
    frame = pd.DataFrame(
        {
            ("AAA", "Close"): [1.0, 2.0],
            ("BBB", "Close"): [3.0, 4.0],
        },
        index=pd.date_range("2020-01-01", periods=2, tz="UTC"),
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=["symbol", "feature"])

    close = features.close_from_ohlcv(frame)

    assert list(close.columns) == ["AAA", "BBB"]
    assert features.feature_from_ohlcv(frame, "Close").equals(close)
