from __future__ import annotations

from typing import Any

import pandas as pd

from research.aegis_research.labels import LabelConfig, LabelResult, build_label_result


def native_label_result(
    close: pd.DataFrame,
    *,
    high: pd.DataFrame | None = None,
    low: pd.DataFrame | None = None,
    **_kwargs: Any,
) -> LabelResult:
    return build_label_result(close, LabelConfig(), high=high, low=low)
