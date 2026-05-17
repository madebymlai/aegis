from __future__ import annotations

import pandas as pd

from research.aegis_research.config import SignalConfig


def probabilities_to_signals(
    positive_class_probability: pd.DataFrame,
    config: SignalConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    entries = positive_class_probability > config.long_threshold
    exits = positive_class_probability < config.exit_threshold
    return entries.fillna(False), exits.fillna(False)
