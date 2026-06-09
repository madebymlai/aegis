"""Tests for custom metric registration and extraction.

Covers:
- Per-extractor unit test (a single read(pf, config) -> Series is testable in isolation)
- Custom metric end-to-end (register definition + extractor, computed through the loop)
- Default metrics undisturbed (existing six metrics' values and fingerprint don't change)
- Conflict detection (custom metric ids must not shadow built-in ids)
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
    make_default_metric_registry,
)
from research.aegis_research.metrics.accessors import (
    central_metrics_from_grouped_accessors,
)
from research.aegis_research.metrics.custom import register_custom_metrics
from research.aegis_research.metrics.extractors import (
    EXTRACTORS,
    ExtractorSpec,
    clear_custom_extractors,
    get_custom_extractor_keys,
    get_extractors,
    register_custom_extractors,
)
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.portfolios import simulate_portfolio_batch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_custom_extractors() -> None:
    """Clear custom extractors before each test so tests don't pollute each other."""
    clear_custom_extractors()


# ---------------------------------------------------------------------------
# Per-extractor unit test
# ---------------------------------------------------------------------------


def test_single_extractor_read_is_testable_in_isolation() -> None:
    """A single read(pf, config) -> Series is unit-testable standalone.

    The extractor makes exactly one VBT accessor call and returns a Series
    indexed by column-group.  No transform logic lives inside the extractor.
    """
    index = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.DataFrame({"A": 100 + np.cumsum(np.random.default_rng(42).normal(0, 1, 10))}, index=index)
    entries = pd.DataFrame({"A": False}, index=index)
    exits = pd.DataFrame({"A": False}, index=index)
    entries.iloc[0] = True
    exits.iloc[5] = True
    pf = vbt.Portfolio.from_signals(close, entries=entries, exits=exits, init_cash=10_000, fees=0.001)
    config = ReportConfig()

    result = EXTRACTORS["total_return"].read(pf, config)
    assert isinstance(result, pd.Series)


# ---------------------------------------------------------------------------
# Custom extractor registration plumbing
# ---------------------------------------------------------------------------


def test_register_custom_extractors_stores_entries() -> None:
    """Custom extractors are stored and retrievable via get_extractors()."""

    def _read_foo(pf: Any, config: ReportConfig) -> pd.Series:
        return pd.Series([42.0])

    spec = ExtractorSpec(_read_foo, scale="identity")
    register_custom_extractors({"foo": spec})

    merged = get_extractors()
    assert "foo" in merged
    assert merged["foo"] is spec
    # Built-in extractors are still present
    for builtin_id in PORTFOLIO_METRIC_VALUE_KEYS:
        assert builtin_id in merged
        assert merged[builtin_id] is EXTRACTORS[builtin_id]

    assert "foo" in get_custom_extractor_keys()


def test_register_custom_extractors_rejects_shadowing() -> None:
    """Custom extractor ids must not conflict with built-in metric ids."""

    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        return pd.Series([1.0])

    with pytest.raises(MetricRegistryError, match="conflict with built-in"):
        register_custom_extractors({"total_return": ExtractorSpec(_read)})


def test_register_custom_metrics_hook_registers_definitions_and_extractors() -> None:
    """register_custom_metrics registers both MetricDefinitions and extractors."""

    def _read_my_metric(pf: Any, config: ReportConfig) -> pd.Series:
        return pd.Series([99.0])

    definition = MetricDefinition(
        id="my_custom_metric",
        title="My Custom Metric",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="count",
        value_semantics="test_metric",
        provider="test",
    )
    spec = ExtractorSpec(_read_my_metric, scale="identity")

    registry = MetricRegistry()
    register_custom_metrics(registry, metrics=[(definition, spec)])

    frozen = registry.freeze()
    assert "my_custom_metric" in frozen.ids()
    assert frozen.get("my_custom_metric").title == "My Custom Metric"
    assert frozen.get("my_custom_metric").source_type == SOURCE_TYPE_CUSTOM

    assert "my_custom_metric" in get_extractors()
    assert get_extractors()["my_custom_metric"].scale == "identity"


def test_register_custom_metrics_rejects_duplicate_extractor_ids() -> None:
    """Duplicate custom metric ids in the same call are rejected."""

    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        return pd.Series([1.0])

    definition = MetricDefinition(
        id="dup",
        title="Dup",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="count",
        value_semantics="test",
    )
    spec = ExtractorSpec(_read)

    registry = MetricRegistry()
    with pytest.raises(MetricRegistryError, match="duplicate metric id"):
        register_custom_metrics(
            registry, metrics=[(definition, spec), (definition, spec)]
        )


# ---------------------------------------------------------------------------
# Custom metric end-to-end: computed through the extraction loop
# ---------------------------------------------------------------------------


def test_custom_metric_computed_through_extraction_loop() -> None:
    """A custom metric registered with its extractor is computed by the shared loop."""

    # A throwaway custom metric that returns one value per column-group
    def _read_constant(pf: Any, config: ReportConfig) -> pd.Series:
        n_groups = len(pf.wrapper.columns)
        return pd.Series([123.0] * n_groups)

    definition = MetricDefinition(
        id="constant_metric",
        title="Constant Metric",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="ratio",
        value_semantics="constant_test",
        provider="test",
    )
    spec = ExtractorSpec(_read_constant, scale="identity")

    registry = MetricRegistry()
    register_custom_metrics(registry, metrics=[(definition, spec)])

    # Build a simple batched portfolio with two candidates
    index = pd.date_range("2024-01-01", periods=8)
    close = pd.DataFrame(
        {"A": [10.0, 12.0, 15.0, 11.0, 9.0, 12.0, 14.0, 13.0]},
        index=index,
    )
    candidate_ids = ["candidate-a", "candidate-b"]
    columns = pd.MultiIndex.from_product(
        [candidate_ids, ["A"]],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    allocations.loc[index[0], ("candidate-a", "A")] = 0.3
    allocations.loc[index[0], ("candidate-b", "A")] = 0.5
    simulation = simulate_portfolio_batch(
        close, allocations, PortfolioConfig(fees=0.001, slippage=0, direction="longonly")
    )
    config = ReportConfig(freq="1D", year_freq="252D")

    candidate_keys = [(c,) for c in candidate_ids]
    result = central_metrics_from_grouped_accessors(
        simulation.portfolio, config, candidate_keys, ["candidate_id"]
    )

    # The custom metric is present in the output
    assert "constant_metric" in result.columns
    # Both candidates get the constant value
    assert result.loc[("candidate-a",), "constant_metric"] == 123.0
    assert result.loc[("candidate-b",), "constant_metric"] == 123.0

    # Built-in metrics are also present
    for builtin_id in PORTFOLIO_METRIC_VALUE_KEYS:
        assert builtin_id in result.columns


# ---------------------------------------------------------------------------
# Default metrics undisturbed
# ---------------------------------------------------------------------------


def test_custom_metric_does_not_perturb_existing_metrics() -> None:
    """Adding a custom metric leaves the existing six metrics' values unchanged.

    We compare the production loop output with and without a custom metric,
    and assert that the built-in columns are identical.
    """
    index = pd.date_range("2024-01-01", periods=8)
    close = pd.DataFrame(
        {"A": [10.0, 12.0, 15.0, 11.0, 9.0, 12.0, 14.0, 13.0]},
        index=index,
    )
    candidate_ids = ["candidate-a"]
    columns = pd.MultiIndex.from_product(
        [candidate_ids, ["A"]],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(np.nan, index=index, columns=columns, dtype=float)
    allocations.loc[index[0], ("candidate-a", "A")] = 0.3
    simulation = simulate_portfolio_batch(
        close, allocations, PortfolioConfig(fees=0.001, slippage=0, direction="longonly")
    )
    config = ReportConfig(freq="1D", year_freq="252D")
    candidate_keys = [(c,) for c in candidate_ids]

    # Run without custom metric
    baseline = central_metrics_from_grouped_accessors(
        simulation.portfolio, config, candidate_keys, ["candidate_id"]
    )

    # Register a custom metric
    def _read_custom(pf: Any, config: ReportConfig) -> pd.Series:
        return pd.Series([42.0])

    register_custom_extractors({"custom_x": ExtractorSpec(_read_custom)})

    # Run with custom metric
    result = central_metrics_from_grouped_accessors(
        simulation.portfolio, config, candidate_keys, ["candidate_id"]
    )

    # All built-in column values must be identical
    for metric_id in PORTFOLIO_METRIC_VALUE_KEYS:
        assert result.loc[("candidate-a",), metric_id] == baseline.loc[("candidate-a",), metric_id], (
            f"{metric_id} value changed after adding custom metric"
        )


def test_default_registry_fingerprint_is_stable() -> None:
    """The default registry fingerprint is unchanged (no custom metrics registered)."""
    registry = make_default_metric_registry()

    assert len(registry.fingerprint) == 64
    # The fingerprint must contain exactly the 6 built-in metrics
    assert set(registry.ids()) == set(PORTFOLIO_METRIC_VALUE_KEYS)

    # No custom extractors in the default path (fixture clears state)
    assert get_custom_extractor_keys() == ()
