"""Indicator precompute store.

Indicator outputs computed **once over the full series** for a fixed set of
sampled candidates, held candidate-major (each candidate owns a contiguous
``n_symbols`` column block) and aligned to the full-series index. The simulate
stage slices this store to a split window by row range and gathers the columns
for the candidates in the current chunk.

Causality contract
------------------
Because the simulate stage reads only the values inside a window while the
indicator was computed over the whole series, this design is leak-free **only
while every indicator is strictly causal** (the value at bar ``t`` depends only
on bars ``<= t``). A non-causal transform (centered window, ``shift(-k)``,
full-series z-score) would inject future bars into the window.

``validate_precompute_no_lookahead`` encodes the contract as a prefix-equivalence
invariant: for each checked row, slicing a full-series store must match
recomputing the same precompute stage on data truncated immediately after that
row and then slicing that prefix store. That permits warmup history before the
row while rejecting dependence on any future row.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from operator import index as operator_index
from typing import Any

import numpy as np

CandidateKey = tuple
CandidateIndex = Mapping[CandidateKey, int]


def canonical_param_order(names: Iterable[str]) -> list[str]:
    """The one canonical element order for a ``CandidateKey``: param names, sorted.

    A ``CandidateKey`` is a positional tuple, so its meaning depends entirely on the
    order its elements are placed in. Every path that builds or reads a key orders it
    through this function — the precompute/store-addressing path (``candidate_keys``)
    and the scored-grid path (``CandidateGrid.param_levels``) — so a key built by one
    path compares equal to the same candidate's key built by the other. Owning the
    order in one place is what stops those paths from silently drifting (aegis-rd-948).
    """
    return sorted(names)


def candidate_keys(param_lists: Mapping[str, Sequence]) -> list[CandidateKey]:
    """Canonical per-candidate identity tuples for a materialised candidate set.

    Tuple elements follow :func:`canonical_param_order` (sorted param name) so every
    stage — the precompute store, the simulate-stage lookup, and the scored grid —
    addresses a candidate by the same key, regardless of the kwargs order the framework
    hands each stage.
    """
    names = canonical_param_order(param_lists)
    n_candidates = len(param_lists[names[0]]) if names else 0
    return [tuple(param_lists[name][i] for name in names) for i in range(n_candidates)]


def build_candidate_index(param_lists: Mapping[str, Sequence]) -> dict[CandidateKey, int]:
    """Map each candidate's canonical key to its column-block position."""
    return {key: position for position, key in enumerate(candidate_keys(param_lists))}


class PrecomputeCausalityError(AssertionError):
    """Raised when a precompute stage's full-series outputs depend on future rows."""


def validate_precompute_no_lookahead(
    precompute: Callable[..., IndicatorPrecompute],
    close,
    *,
    ranges: Sequence[slice],
    n_candidates: int,
    **param_lists: Sequence,
) -> None:
    """Validate the prefix-equivalence no-look-ahead contract for ``precompute``.

    The full-series precompute store is safe to slice into split windows only if
    each row is unchanged when the source series is truncated immediately after
    that row. This check allows causal warmup history before the row and detects
    outputs that use future rows (for example ``shift(-1)``, centered windows, or
    full-series normalization).
    """
    full_store = precompute(close, n_candidates, **param_lists)
    keys = candidate_keys(param_lists)
    close_length = len(close)

    for range_ in ranges:
        start, stop = _prefix_comparison_bounds(range_, close_length)
        for row in range(start, stop):
            comparison_range = slice(row, row + 1)
            prefix_store = precompute(close.iloc[: row + 1], n_candidates, **param_lists)
            _assert_windows_equal(
                full_store.window(comparison_range, keys),
                prefix_store.window(comparison_range, keys),
                range_=comparison_range,
            )


def _prefix_comparison_bounds(range_: slice, full_len: int) -> tuple[int, int]:
    if range_.step not in (None, 1):
        raise ValueError("precompute no-look-ahead validation supports only contiguous slices")
    start = 0 if range_.start is None else _non_negative_slice_bound(range_.start, "start")
    stop = full_len if range_.stop is None else _non_negative_slice_bound(range_.stop, "stop")
    if stop < start:
        raise ValueError("precompute no-look-ahead validation requires stop >= start")
    if stop > full_len:
        raise ValueError("precompute no-look-ahead validation range exceeds close length")
    return start, stop


def _non_negative_slice_bound(value, name: str) -> int:
    bound = operator_index(value)
    if bound < 0:
        raise ValueError(
            f"precompute no-look-ahead validation requires non-negative {name} bounds"
        )
    return bound


def _assert_windows_equal(
    full_window: Mapping[str, np.ndarray],
    prefix_window: Mapping[str, np.ndarray],
    *,
    range_: slice,
) -> None:
    full_output_names = set(full_window)
    prefix_output_names = set(prefix_window)
    if full_output_names != prefix_output_names:
        raise PrecomputeCausalityError(
            "precompute outputs differ between full-series and prefix-only recompute "
            f"for range {range_}: full={sorted(full_output_names)}, "
            f"prefix={sorted(prefix_output_names)}"
        )
    for output_name in sorted(full_output_names):
        full_arr = np.asarray(full_window[output_name])
        prefix_arr = np.asarray(prefix_window[output_name])
        if full_arr.shape != prefix_arr.shape:
            raise PrecomputeCausalityError(
                f"precompute output {output_name!r} shape differs for range {range_}: "
                f"full={full_arr.shape}, prefix={prefix_arr.shape}"
            )
        if not np.array_equal(full_arr, prefix_arr, equal_nan=True):
            raise PrecomputeCausalityError(
                f"precompute output {output_name!r} for range {range_} depends on future rows; "
                "full-series values differ from prefix-only recompute"
            )


@dataclass(frozen=True)
class IndicatorPrecompute:
    """Full-series indicator outputs addressable by candidate and sliceable by range.

    ``candidate_index`` is the default full-candidate block map. Individual outputs
    may provide ``output_candidate_index`` when their indicator was computed only
    for unique indicator-parameter tuples; ``window`` then expands those deduped
    blocks back to the requested full-candidate order.
    """

    outputs: Mapping[str, np.ndarray]
    candidate_index: CandidateIndex
    n_symbols: int
    output_candidate_index: Mapping[str, CandidateIndex] | None = None

    def window(
        self, range_: slice, keys: Sequence[CandidateKey]
    ) -> dict[str, np.ndarray]:
        """Rows in ``range_`` by the candidate-major columns for ``keys``, in order."""
        windowed: dict[str, np.ndarray] = {}
        for name, array in self.outputs.items():
            candidate_index = self._candidate_index_for_output(name)
            positions = [candidate_index[key] for key in keys]
            blocks = [
                array[range_, position * self.n_symbols : (position + 1) * self.n_symbols]
                for position in positions
            ]
            windowed[name] = np.concatenate(blocks, axis=1) if blocks else array[range_, :0]
        return windowed

    def _candidate_index_for_output(self, name: str) -> CandidateIndex:
        if self.output_candidate_index is None:
            return self.candidate_index
        return self.output_candidate_index.get(name, self.candidate_index)

    @cached_property
    def invalid_keys(self) -> set[CandidateKey]:
        """Keys of the store's candidates whose indicator output is Invalid.

        A candidate is Invalid when at least one indicator output block is
        entirely non-finite (all-NaN / all-inf) over the full series — the
        indicator's lookback exceeds all available history. A non-numeric output
        block is a broken indicator contract and raises ``TypeError`` rather than
        being classified. The scan ranges over the store's own ``candidate_index``:
        the store is the authority on which candidates it holds.

        Cached because the verdict is a pure function of the store's immutable
        outputs and every reader wants the same set. ``cached_property`` writes to
        ``__dict__`` (bypassing the frozen ``__setattr__``), so when the runner
        touches this once before the parallel sweep, dill ships the warm cache to
        every pathos worker instead of each worker re-scanning the full series.
        """
        if not self.outputs or self.n_symbols < 1:
            return set()
        invalid: set[CandidateKey] = set()
        for key in self.candidate_index:
            for output_name, output in self.outputs.items():
                position = self._candidate_index_for_output(output_name)[key]
                if _candidate_output_is_non_finite(output, position, self.n_symbols):
                    invalid.add(key)
                    break
        return invalid


def _candidate_output_is_non_finite(output: Any, position: int, n_symbols: int) -> bool:
    start = position * n_symbols
    stop = start + n_symbols
    block = np.asarray(output)[:, start:stop]
    return block.size == 0 or not _has_finite_value(block)


def _has_finite_value(values: Any) -> bool:
    # A non-numeric block is a broken Indicator contract: np.isfinite raises
    # TypeError and the failure propagates instead of being classified.
    return bool(np.isfinite(values).any())


def empty_precompute(
    close, n_candidates: int, **param_lists: Sequence
) -> IndicatorPrecompute:
    """Store with no indicator outputs, for strategy-only sources (no indicators).

    The simulate stage ignores the (empty) windowed outputs and computes
    allocations directly from the price window.
    """
    return IndicatorPrecompute(
        outputs={},
        candidate_index=build_candidate_index(param_lists),
        n_symbols=len(close.columns),
    )
