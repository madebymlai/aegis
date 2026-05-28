"""Wide indicator precompute store.

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
full-series z-score) would inject future bars into the window. The permanent
no-future-leak invariant that enforces this is a sibling slice
(``aegis-rd-94v.4``); this module documents the precondition it assumes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

CandidateKey = tuple
CandidateIndex = Mapping[CandidateKey, int]


def candidate_keys(param_lists: Mapping[str, Sequence]) -> list[CandidateKey]:
    """Canonical per-candidate identity tuples for a materialised candidate set.

    The tuple is built in sorted param-name order so the precompute store and the
    simulate-stage lookup agree regardless of the kwargs order the framework hands
    each stage. The ordering is internal to store addressing and is independent of
    the metric-row candidate identity used by the central-metrics step.
    """
    names = sorted(param_lists)
    n_candidates = len(param_lists[names[0]]) if names else 0
    return [tuple(param_lists[name][i] for name in names) for i in range(n_candidates)]


def build_candidate_index(param_lists: Mapping[str, Sequence]) -> dict[CandidateKey, int]:
    """Map each candidate's canonical key to its column-block position."""
    return {key: position for position, key in enumerate(candidate_keys(param_lists))}


@dataclass(frozen=True)
class WideIndicatorPrecompute:
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


def empty_precompute(
    close, n_candidates: int, **param_lists: Sequence
) -> WideIndicatorPrecompute:
    """Store with no indicator outputs, for strategy-only sources (no indicators).

    The simulate stage ignores the (empty) windowed outputs and computes
    allocations directly from the price window.
    """
    return WideIndicatorPrecompute(
        outputs={},
        candidate_index=build_candidate_index(param_lists),
        n_symbols=len(close.columns),
    )
