from __future__ import annotations

import pandas as pd

from research.aegis_research.config import SignalConfig


def probabilities_to_signals(
    long_probability: pd.Series,
    config: SignalConfig,
) -> tuple[pd.Series, pd.Series]:
    entries = long_probability > config.long_threshold
    exits = long_probability < config.exit_threshold
    entries = entries.fillna(False).rename("entry")
    exits = exits.fillna(False).rename("exit")
    return entries, exits
