"""Candidate Grid: frozen value object wrapping a sweep's row-stacked scored table.

Owns the shape contract (MultiIndex, split level, at least one parameter level),
the split-level literal, parameter-level derivation, NaN-to-None normalization,
and the candidate-wise iteration with a documented parameter-sorted order guarantee.

This module imports nothing from the runner. It imports pandas (for the private
spine) and the CandidateKey alias from precompute.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from math import isnan
from typing import Any

import pandas as pd

from research.aegis_research.optimization.precompute import CandidateKey

_SPLIT_LEVEL = "split"


@dataclass(frozen=True)
class CandidateGrid:
    """Frozen value object over a private DataFrame spine.

    Constructed via ``from_sweep`` at the sweep seam or directly with a compliant
    frame (tests). Every instance is valid by construction — the post-init check
    rejects malformed frames before any consumer sees them.

    The public surface is plain mappings: ``by_candidate()`` yields per-Candidate
    ``(CandidateKey, split → metric_id → float-or-None)`` with NaN normalized to
    None and a documented parameter-sorted iteration guarantee. No rectangular
    completeness promise is made: ``by_candidate()`` yields the Splits actually
    swept.
    """

    _spine: pd.DataFrame

    def __post_init__(self) -> None:
        idx = self._spine.index
        if not isinstance(idx, pd.MultiIndex):
            raise TypeError("CandidateGrid index must be a MultiIndex")
        if _SPLIT_LEVEL not in idx.names:
            raise ValueError(
                f"CandidateGrid index must include a {_SPLIT_LEVEL!r} level"
            )
        param_levels = [n for n in idx.names if n != _SPLIT_LEVEL]
        if not param_levels:
            raise ValueError(
                "CandidateGrid index must carry at least one parameter level"
            )

    @classmethod
    def from_sweep(cls, stacked: pd.DataFrame) -> CandidateGrid:
        """Absorb the runner's tidy step and delegate to the validating constructor.

        ``stacked`` is the raw return value of ``vbt.Splitter.apply(...,
        merge_func="row_stack")`` with a single set selected. The row-stack guard
        (DataFrame + MultiIndex) lives here; normalization (copy, strip columns
        name) happens once before validation.
        """
        if not isinstance(stacked, pd.DataFrame):
            raise TypeError(
                "sweep must row-stack into a DataFrame; "
                f"got {type(stacked).__name__}"
            )
        if not isinstance(stacked.index, pd.MultiIndex):
            raise TypeError(
                "sweep DataFrame must carry a MultiIndex; "
                f"got {type(stacked.index).__name__}"
            )
        tidy = stacked.copy()
        tidy.columns.name = None
        return cls(tidy)

    # -- read surface ----------------------------------------------------------

    @property
    def param_levels(self) -> list[str]:
        """Parameter level names (all index levels except the split level)."""
        return [n for n in self._spine.index.names if n != _SPLIT_LEVEL]

    @property
    def metric_ids(self) -> list[str]:
        """Metric column names in column order."""
        return list(self._spine.columns)

    def by_candidate(
        self,
    ) -> Iterator[tuple[CandidateKey, dict[Any, dict[str, float | None]]]]:
        """Yield (CandidateKey, split → metric_id → float-or-None) in parameter-sorted order.

        NaN values are normalized to None. Iteration order is deterministic:
        parameter-sorted grouping with ``sort=True``.
        """
        param_levels = self.param_levels
        group_level = param_levels[0] if len(param_levels) == 1 else param_levels
        metric_cols = self.metric_ids
        for key, sub in self._spine.groupby(level=group_level, sort=True):
            key_tuple: CandidateKey = key if isinstance(key, tuple) else (key,)
            result: dict[Any, dict[str, float | None]] = {}
            sub_splits = sub.index.get_level_values(_SPLIT_LEVEL)
            for split_label, (_, row) in zip(sub_splits, sub.iterrows(), strict=True):
                result[split_label] = {
                    col: _nan_to_none(row[col]) for col in metric_cols
                }
            yield (key_tuple, result)

    def split_metrics(
        self, key: CandidateKey
    ) -> dict[Any, dict[str, float | None]]:
        """Point lookup: return the split→metric_id→float-or-None mapping for one Candidate."""
        param_levels = self.param_levels
        if len(param_levels) == 1:
            sub = self._spine.xs(key[0], level=param_levels[0])
        else:
            sub = self._spine.xs(key, level=param_levels)
        result: dict[Any, dict[str, float | None]] = {}
        metric_cols = self.metric_ids
        for split_label, (_, row) in zip(sub.index, sub.iterrows(), strict=True):
            result[split_label] = {
                col: _nan_to_none(row[col]) for col in metric_cols
            }
        return result


def _nan_to_none(value: Any) -> float | None:
    """Normalize a scalar to float or None, converting NaN to None."""
    if value is None:
        return None
    number = float(value)
    return None if isnan(number) else number
