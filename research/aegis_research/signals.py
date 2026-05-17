from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import SignalConfig
from research.aegis_research.model_contracts import POSITIVE_CLASS_PROBABILITY

SIGNAL_DIAGNOSTICS_SCHEMA_VERSION = "signal_diagnostics.v1"
SIGNAL_POLICY_VERSION = 1
SIGNAL_CLEANING_SETTINGS = {
    "force_first": True,
    "keep_conflicts": False,
    "reverse_order": False,
}


@dataclass(frozen=True)
class SignalResult:
    entries: pd.DataFrame
    exits: pd.DataFrame
    diagnostics: dict[str, Any]


def probabilities_to_signals(
    positive_class_probability: pd.DataFrame,
    config: SignalConfig,
    *,
    probability_metadata: Mapping[str, Any] | None = None,
    split_id: str | None = None,
    set_name: str | None = None,
) -> SignalResult:
    entries = positive_class_probability.gt(config.long_entry_threshold).fillna(False).astype(bool)
    exits = positive_class_probability.lt(config.long_exit_threshold).fillna(False).astype(bool)
    diagnostics = _build_signal_diagnostics(
        positive_class_probability,
        entries,
        exits,
        config,
        probability_metadata=probability_metadata,
        split_id=split_id,
        set_name=set_name,
    )
    return SignalResult(entries=entries, exits=exits, diagnostics=diagnostics)


def _build_signal_diagnostics(
    positive_class_probability: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    config: SignalConfig,
    *,
    probability_metadata: Mapping[str, Any] | None,
    split_id: str | None,
    set_name: str | None,
) -> dict[str, Any]:
    cleaned_entries, cleaned_exits = vbt.SignalsAccessor.clean(
        entries,
        exits,
        **SIGNAL_CLEANING_SETTINGS,
    )
    return {
        "schema_version": SIGNAL_DIAGNOSTICS_SCHEMA_VERSION,
        "split_id": split_id,
        "set_name": set_name,
        "policy": {
            "name": config.policy,
            "version": SIGNAL_POLICY_VERSION,
            "long_entry_threshold": float(config.long_entry_threshold),
            "long_exit_threshold": float(config.long_exit_threshold),
            "comparison": {
                "entry": "positive_class_probability > long_entry_threshold",
                "exit": "positive_class_probability < long_exit_threshold",
                "threshold_equality": "hold_band_no_action",
            },
        },
        "execution": {"timing": config.execution_timing},
        "probability": _probability_payload(probability_metadata),
        "counts": _signal_counts(positive_class_probability, entries, exits),
        "cleaned_diagnostics": {
            "diagnostics_only": True,
            "settings": dict(SIGNAL_CLEANING_SETTINGS),
            "by_symbol": _cleaned_counts_by_symbol(cleaned_entries, cleaned_exits),
            "clean_entry_states": _true_count(cleaned_entries),
            "clean_exit_states": _true_count(cleaned_exits),
        },
    }


def _probability_payload(probability_metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    metadata = dict(probability_metadata or {})
    return {
        "source_output_name": metadata.get(
            "source_output_name",
            metadata.get("output_name", POSITIVE_CLASS_PROBABILITY),
        ),
        "positive_class": metadata.get("positive_class"),
        "calibrated": metadata.get("calibrated", False),
        "threshold_tuned": metadata.get("threshold_tuned", False),
        "metadata": metadata,
    }


def _signal_counts(
    positive_class_probability: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
) -> dict[str, Any]:
    missing = positive_class_probability.isna()
    simultaneous = entries & exits
    return {
        "total_cells": int(positive_class_probability.size),
        "missing_probabilities": _true_count(missing),
        "raw_entry_states": _true_count(entries),
        "raw_exit_states": _true_count(exits),
        "simultaneous_entry_exit_states": _true_count(simultaneous),
        "by_symbol": {
            str(column): {
                "total_cells": len(positive_class_probability.index),
                "missing_probabilities": _true_count(missing.loc[:, column]),
                "raw_entry_states": _true_count(entries.loc[:, column]),
                "raw_exit_states": _true_count(exits.loc[:, column]),
                "simultaneous_entry_exit_states": _true_count(simultaneous.loc[:, column]),
            }
            for column in positive_class_probability.columns
        },
    }


def _cleaned_counts_by_symbol(
    cleaned_entries: pd.DataFrame,
    cleaned_exits: pd.DataFrame,
) -> dict[str, dict[str, int]]:
    return {
        str(column): {
            "clean_entry_states": _true_count(cleaned_entries.loc[:, column]),
            "clean_exit_states": _true_count(cleaned_exits.loc[:, column]),
        }
        for column in cleaned_entries.columns
    }


def _true_count(value: pd.DataFrame | pd.Series) -> int:
    return int(value.to_numpy(dtype=bool).sum())
