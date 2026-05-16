from __future__ import annotations

import pandas as pd

from research.aegis_research.config import LabelConfig


def build_labels(close: pd.Series | pd.DataFrame, config: LabelConfig) -> pd.Series:
    close_series = _primary_close(close)
    forward_return = close_series.shift(-config.horizon) / close_series - 1
    labels = (forward_return > config.threshold).astype("Int8")
    labels[forward_return.isna()] = pd.NA
    return labels.rename("label")


def _primary_close(close: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(close, pd.Series):
        return close
    return close.iloc[:, 0].rename(str(close.columns[0]))
