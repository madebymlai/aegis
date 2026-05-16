from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import SplitConfig


@dataclass(frozen=True)
class ValidationSplit:
    label: str
    train_index: pd.Index
    test_index: pd.Index


def build_validation_splits(index: pd.Index, config: SplitConfig) -> list[ValidationSplit]:
    if config.kind == "holdout":
        return [_chronological_split(index, config)]
    if config.kind == "rolling":
        return _rolling_splits(index, config)
    raise ValueError(f"Unsupported split kind: {config.kind}")


def _chronological_split(index: pd.Index, config: SplitConfig) -> ValidationSplit:
    if not 0 < config.train_size < 1:
        raise ValueError("split.train_size must be between 0 and 1")
    split_at = int(len(index) * config.train_size)
    test_start = min(len(index), split_at + config.embargo_bars)
    return ValidationSplit(label="holdout", train_index=index[:split_at], test_index=index[test_start:])


def _rolling_splits(index: pd.Index, config: SplitConfig) -> list[ValidationSplit]:
    if config.n < 2:
        raise ValueError("split.n must be at least 2 for rolling validation")
    if not 0 < config.train_size < 1:
        raise ValueError("split.train_size must be between 0 and 1")

    splitter = vbt.Splitter.from_n_rolling(
        index,
        n=config.n,
        length=config.length,
        split=config.train_size,
        optimize_anchor_set=1,
        set_labels=["train", "test"],
    )
    index_slices = splitter.take(index)
    splits: list[ValidationSplit] = []
    for split_label in index_slices.index.get_level_values("split").unique():
        train_index = index_slices.loc[(split_label, "train")]
        test_index = index_slices.loc[(split_label, "test")]
        if config.embargo_bars:
            test_index = test_index[config.embargo_bars :]
        if len(train_index) == 0 or len(test_index) == 0:
            raise ValueError(f"Split {split_label} produced an empty train or test range")
        splits.append(
            ValidationSplit(
                label=f"split_{split_label}",
                train_index=train_index,
                test_index=test_index,
            )
        )
    return splits
