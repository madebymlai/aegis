from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from research.aegis_research.config import SplitConfig


@dataclass(frozen=True)
class TrainTestSplit:
    train_index: pd.Index
    test_index: pd.Index


def chronological_split(index: pd.Index, config: SplitConfig) -> TrainTestSplit:
    if not 0 < config.train_size < 1:
        raise ValueError("split.train_size must be between 0 and 1")
    split_at = int(len(index) * config.train_size)
    test_start = min(len(index), split_at + config.embargo_bars)
    return TrainTestSplit(train_index=index[:split_at], test_index=index[test_start:])
