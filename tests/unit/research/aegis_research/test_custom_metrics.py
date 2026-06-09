"""Tests for custom metric registration and extraction.

Covers:
- Per-extractor unit test (a single read(pf, config) -> Series is testable in isolation)
- Custom metric end-to-end (register definition + extractor, computed through the loop)
- Default metrics undisturbed (existing six metrics' values don't change)
- Conflict detection (custom metric ids must not shadow built-in ids)

There is no process-global extractor state to isolate: a custom metric's
extractor lives on the registry record it was registered into, so tests cannot
pollute one another (see ``test_metric_registry`` for the no-leak guarantee).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.config import PortfolioConfig
from research.aegis_research.configuration.schema import ReportConfig
from research.aegis_research.metrics import (
    SOURCE_TYPE_CUSTOM,
    MetricDefinition,
    MetricRegistry,
    MetricRegistryError,
)
from research.aegis_research.metrics.accessors import (
    central_metrics_from_grouped_accessors,
)
from research.aegis_research.metrics.contracts import ExtractorSpec
from research.aegis_research.metrics.custom import register_custom_metrics
from research.aegis_research.metrics.extractors import BUILTIN_EXTRACTORS
from research.aegis_research.metrics.stats import (
    PORTFOLIO_METRIC_VALUE_KEYS,
    register_vbt_stats_metrics,
)
from research.aegis_research.portfolios import simulate_portfolio_batch


def _registry_with_custom(
    metrics: list[tuple[MetricDefinition, ExtractorSpec]] | None = None,
):
    registry = MetricRegistry()
    register_vbt_stats_metrics(registry)
    if metrics:
        register_custom_metrics(registry, metrics=metrics)
    return registry.freeze()


# ---------------------------------------------------------------------------
# Per-extractor unit test
# ---------------------------------------------------------------------------


def test_single_extractor_read_is_testable_in_isolation() -> None:
    """A single read(pf, config) -> Series is unit-testable standalone.

    The extractor makes exactly one VBT accessor call; no transform logic lives
    inside the read.
    """
    index = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.DataFrame({"A": 100 + np.cumsum(np.random.default_rng(42).normal(0, 1, 10))}, index=index)
    entries = pd.DataFrame({"A": False}, index=index)
    exits = pd.DataFrame({"A": False}, index=index)
    entries.iloc[0] = True
    exits.iloc[5] = True
    pf = vbt.Portfolio.from_signals(close, entries=entries, exits=exits, init_cash=10_000, fees=0.001)

    result = BUILTIN_EXTRACTORS["total_return"].read(pf, ReportConfig())
    assert isinstance(result, pd.Series)


# ---------------------------------------------------------------------------
# Registration: definition + extractor as one record
# ---------------------------------------------------------------------------


def test_register_custom_metrics_records_definition_and_extractor() -> None:
    definition = MetricDefinition(
        id="my_custom_metric",
        title="My Custom Metric",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="count",
        value_semantics="test_metric",
        provider="test",
    )
    spec = ExtractorSpec(lambda pf, config: pd.Series([99.0]), scale="identity")

    frozen = _registry_with_custom([(definition, spec)])

    assert frozen.get("my_custom_metric").title == "My Custom Metric"
    assert frozen.extractors["my_custom_metric"] is spec
    assert set(frozen.extractors) == set(frozen.definitions)


def test_register_custom_metric_rejects_shadowing_a_builtin() -> None:
    """A custom id colliding with a built-in is a duplicate registry record."""
    definition = MetricDefinition(
        id="total_return",
        title="Shadow",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="ratio",
        value_semantics="test",
    )

    with pytest.raises(MetricRegistryError, match="duplicate metric id"):
        _registry_with_custom([(definition, ExtractorSpec(lambda pf, config: None))])


def test_register_custom_metrics_rejects_duplicate_in_same_call() -> None:
    definition = MetricDefinition(
        id="dup",
        title="Dup",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="count",
        value_semantics="test",
    )
    spec = ExtractorSpec(lambda pf, config: None)

    registry = MetricRegistry()
    with pytest.raises(MetricRegistryError, match="duplicate metric id"):
        register_custom_metrics(registry, metrics=[(definition, spec), (definition, spec)])


# ---------------------------------------------------------------------------
# Custom metric end-to-end: computed through the extraction loop
# ---------------------------------------------------------------------------


def _two_candidate_portfolio():
    index = pd.date_range("2024-01-01", periods=8)
    close = pd.DataFrame({"A": [10.0, 12.0, 15.0, 11.0, 9.0, 12.0, 14.0, 13.0]}, index=index)
    candidate_ids = ["candidate-a", "candidate-b"]
    columns = pd.MultiIndex.from_product([candidate_ids, ["A"]], names=["candidate_id", "symbol"])
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    allocations.loc[index[0], ("candidate-a", "A")] = 0.3
    allocations.loc[index[0], ("candidate-b", "A")] = 0.5
    simulation = simulate_portfolio_batch(
        close, allocations, PortfolioConfig(fees=0.001, slippage=0, direction="longonly")
    )
    return simulation.portfolio, candidate_ids


def test_custom_metric_computed_through_extraction_loop() -> None:
    def _read_constant(pf: Any, config: ReportConfig) -> pd.Series:
        return pd.Series([123.0] * len(pf.wrapper.columns))

    definition = MetricDefinition(
        id="constant_metric",
        title="Constant Metric",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="ratio",
        value_semantics="constant_test",
        provider="test",
    )
    frozen = _registry_with_custom([(definition, ExtractorSpec(_read_constant))])

    portfolio, candidate_ids = _two_candidate_portfolio()
    result = central_metrics_from_grouped_accessors(
        portfolio,
        ReportConfig(freq="1D", year_freq="252D"),
        [(c,) for c in candidate_ids],
        ["candidate_id"],
        frozen.extractors,
    )

    assert result.loc[("candidate-a",), "constant_metric"] == 123.0
    assert result.loc[("candidate-b",), "constant_metric"] == 123.0
    for builtin_id in PORTFOLIO_METRIC_VALUE_KEYS:
        assert builtin_id in result.columns


def test_custom_metric_does_not_perturb_existing_metrics() -> None:
    """Adding a custom metric leaves the six built-in metric values unchanged."""
    portfolio, candidate_ids = _two_candidate_portfolio()
    config = ReportConfig(freq="1D", year_freq="252D")
    candidate_keys = [(c,) for c in candidate_ids]

    baseline = central_metrics_from_grouped_accessors(
        portfolio, config, candidate_keys, ["candidate_id"], _registry_with_custom().extractors
    )

    definition = MetricDefinition(
        id="custom_x",
        title="Custom X",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="ratio",
        value_semantics="test",
    )
    with_custom = central_metrics_from_grouped_accessors(
        portfolio,
        config,
        candidate_keys,
        ["candidate_id"],
        _registry_with_custom(
            [(definition, ExtractorSpec(lambda pf, c: pd.Series([42.0] * len(pf.wrapper.columns))))]
        ).extractors,
    )

    for metric_id in PORTFOLIO_METRIC_VALUE_KEYS:
        assert (
            with_custom.loc[("candidate-a",), metric_id]
            == baseline.loc[("candidate-a",), metric_id]
        ), f"{metric_id} value changed after adding custom metric"
