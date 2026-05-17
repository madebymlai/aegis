from __future__ import annotations

import pandas as pd

from research.aegis_research.config import SignalConfig


def probabilities_to_signals(
    long_probability: pd.DataFrame,
    config: SignalConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    entries = long_probability > config.long_threshold
    exits = long_probability < config.exit_threshold
    return entries.fillna(False), exits.fillna(False)
