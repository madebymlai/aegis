from __future__ import annotations

from typing import Any

import pandas as pd

from research.aegis_research.labels import LabelConfig, LabelResult, build_label_result
from research.aegis_research.market_data.contracts import MarketDataBundle


def native_label_result(data: MarketDataBundle | pd.DataFrame, **_kwargs: Any) -> LabelResult:
    if isinstance(data, pd.DataFrame):
        close = data
        high = None
        low = None
    else:
        close = data.close
        high = data.high
        low = data.low
    return build_label_result(close, LabelConfig(), high=high, low=low)
