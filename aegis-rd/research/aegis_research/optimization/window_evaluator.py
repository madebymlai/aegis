"""Per-window evaluation of one Candidate chunk.

A :class:`WindowEvaluator` carries everything one optimization sweep needs that
is constant across windows — the signal-side source, the portfolio policy, the
report config, the full-series price frames, the precomputed indicator store
(which answers its own Invalid-Candidate set), and the metric extractors — and
exposes a single ``evaluate(range_, **params)`` that the splitter calls once per
(split, set) with the window's ``range_`` template and a chunk of Candidate
parameter lists.

Pulling this coordination out of the sweep closure gives it a seam: a chunk can
be evaluated directly, so the range/key slicing and the all-Invalid short-circuit
are tested through ``evaluate`` instead of only end to end through
``vbt.parameterized`` + ``Splitter.apply``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from aegis_runtime import DriftBand, InstrumentId
from vectorbtpro import vbt

from research.aegis_research.configuration import PortfolioConfig, ReportConfig
from research.aegis_research.market_data.run_arrays import RunArrays
from research.aegis_research.metrics.accessors import (
    central_metrics_from_grouped_accessors,
)
from research.aegis_research.metrics.contracts import ExtractorSpec
from research.aegis_research.optimization.precompute import (
    IndicatorPrecompute,
    candidate_keys,
)
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.portfolios import simulate_portfolio_batch


@dataclass(frozen=True)
class WindowEvaluator:
    """Evaluate one Candidate chunk over one split window into a metric frame.

    ``arrays`` (the Run's prepared views) and ``store`` are the full-series
    inputs; ``evaluate`` slices them to the window the splitter hands it. The
    market index passed to the portfolio simulation is always the full
    loaded-data calendar so the seam mask can detect gaps in purged/embargoed
    windows. The Invalid-Candidate set is read from ``store.invalid_keys`` rather
    than carried as a separate field, so selection and held-out sweeps — which
    share one evaluator and one store — cannot drift in it or any other captured
    input.
    """

    source: OptimizationSource
    portfolio: PortfolioConfig
    report: ReportConfig
    arrays: RunArrays
    store: IndicatorPrecompute
    extractors: Mapping[str, ExtractorSpec]
    # Per-symbol trade fees (FX-conversion surcharge on non-base legs); None keeps
    # the scalar-fee path, byte-identical to a single-currency book.
    fees_by_symbol: pd.Series | None = None
    # Resolved instrument → DriftBand map (the same one the bundle carries); None gates
    # every instrument at the sleeve-wide default.
    instrument_bands: Mapping[InstrumentId, DriftBand] | None = None
    futures_roots: tuple[str, ...] = ()

    def evaluate(self, range_: slice, **params: Any) -> Any:
        """Metric frame for the Candidate chunk ``params`` over the window ``range_``."""
        param_names, combo_lists, n_combos, metric_keys = _extract_combos(params)
        keys = candidate_keys(combo_lists)
        invalid = self.store.invalid_keys
        if all(key in invalid for key in keys):
            # A chunk whose every Candidate is Invalid is a pure performance guard:
            # skip simulation and return the same-shaped all-NaN frame. Partly-Invalid
            # chunks still simulate; their real values stay in the grid and are excluded
            # by-key downstream via classify_candidates.
            return _nan_metric_frame(metric_keys, param_names, list(self.extractors))

        close_window = self.arrays.pnl_close.iloc[range_]
        open_window = self.arrays.pnl_open.iloc[range_]
        indicator_window = self.store.window(range_, keys)
        allocations = self.source.simulate(
            close_window, indicator_window, n_combos, **combo_lists
        )
        return self._metrics_from_allocations(
            close_window, open_window, allocations, metric_keys, param_names
        )

    def _metrics_from_allocations(
        self,
        close_window: pd.DataFrame,
        open_window: pd.DataFrame,
        allocations: Any,
        metric_keys: list[tuple],
        param_names: list[str],
    ) -> Any:
        if allocations is vbt.NoResult:
            return vbt.NoResult
        n_symbols = len(close_window.columns)
        if n_symbols == 0 or len(allocations.columns) // n_symbols < 1:
            return vbt.NoResult
        pf = simulate_portfolio_batch(
            close_window,
            allocations,
            self.portfolio,
            open_=open_window,
            market_index=self.arrays.pnl_close.index,
            periods_per_year=self.report.periods_per_year,
            fees_by_symbol=self.fees_by_symbol,
            instrument_bands=self.instrument_bands,
            futures_roots=self.futures_roots,
            distributions=self.arrays.distributions,
            currency_conversion=self.arrays.currency_conversion,
        )
        return central_metrics_from_grouped_accessors(
            pf, self.report, metric_keys, param_names, self.extractors
        )


def _extract_combos(
    params: Mapping[str, Any],
) -> tuple[list[str], dict[str, list[Any]], int, list[tuple]]:
    # Under mono-chunking every parameter arrives as a list of the chunk's per-combo
    # values (a single-element list for a one-combo chunk). The grouped accessor
    # returns one metric row per combo, owning the parameter MultiIndex that vbt
    # row-stacks across chunks and splits.
    param_names = list(params)
    combo_lists = {name: _combo_values(value) for name, value in params.items()}
    n_combos = len(combo_lists[param_names[0]]) if param_names else 0
    metric_keys = [
        tuple(combo_lists[name][i] for name in param_names) for i in range(n_combos)
    ]
    return param_names, combo_lists, n_combos, metric_keys


def _combo_values(value: Any) -> list[Any]:
    """Normalize a mono-chunk parameter into its list of per-combo values.

    Under mono-chunking vbt passes each parameter as the chunk's list of values;
    a single-combo chunk (or a ``skip_single_comb`` shortcut) arrives as a scalar.
    """
    if pd.api.types.is_list_like(value):
        return list(value)
    return [value]


def _nan_metric_frame(
    metric_keys: list[tuple], param_names: list[str], metric_ids: list[str]
) -> pd.DataFrame:
    # float64 by construction — same grid dtype contract as
    # central_metrics_from_grouped_accessors, so vbt's row_stack concat
    # never has to reconcile divergent dtypes across windows. Columns mirror
    # the registry's extractor set so custom metrics stay aligned.
    index = pd.MultiIndex.from_tuples(metric_keys, names=param_names)
    return pd.DataFrame(np.nan, index=index, columns=metric_ids)
