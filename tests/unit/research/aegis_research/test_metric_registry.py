from __future__ import annotations

import pytest

from research.aegis_research.metrics import (
    SOURCE_TYPE_VBT_STATS,
    MetricDefinition,
    MetricRegistry,
    MetricRegistryError,
    make_default_metric_registry,
)
from research.aegis_research.metrics.contracts import ExtractorSpec
from research.aegis_research.metrics.extractors import BUILTIN_EXTRACTORS
from research.aegis_research.metrics.stats import (
    PORTFOLIO_METRIC_VALUE_KEYS,
    register_vbt_stats_metrics,
)

_SPEC = ExtractorSpec(lambda pf, config: None)
_STATS_TITLES = {m: {"title": m} for m in PORTFOLIO_METRIC_VALUE_KEYS}


def test_metric_registry_freezes_definitions_and_fingerprint() -> None:
    registry = MetricRegistry()
    registry.register(_definition("sharpe_ratio", title="Sharpe Ratio"), _SPEC)
    registry.register(_definition("total_return", title="Total Return"), _SPEC)

    frozen = registry.freeze()

    assert frozen.ids() == ("sharpe_ratio", "total_return")
    assert frozen.get("total_return").title == "Total Return"
    assert len(frozen.fingerprint) == 64


def test_register_requires_an_extractor() -> None:
    """A definition cannot enter the registry without a way to compute it.

    Catalog-only drift is a missing argument at the call site, fail-closed at
    startup — not a KeyError discovered mid-extraction.
    """
    registry = MetricRegistry()

    with pytest.raises(TypeError):
        registry.register(_definition("total_return"))  # type: ignore[call-arg]


def test_frozen_registry_extractors_match_definitions() -> None:
    """Every frozen definition has exactly one extractor and vice versa."""
    registry = MetricRegistry()
    registry.register(_definition("total_return"), _SPEC)
    registry.register(_definition("sharpe_ratio"), _SPEC)

    frozen = registry.freeze()

    assert set(frozen.extractors) == set(frozen.definitions)


def test_default_registry_extractors_match_definitions() -> None:
    frozen = make_default_metric_registry()

    assert set(frozen.extractors) == set(frozen.definitions)


def test_default_registry_extractors_preserve_catalog_order() -> None:
    """Extractor iteration order is registration (catalog) order, not sorted id order.

    The extraction loop's column order is this iteration order, so it must match
    the catalog rather than the fingerprint's sorted definition order.
    """
    frozen = make_default_metric_registry()

    assert tuple(frozen.extractors) == PORTFOLIO_METRIC_VALUE_KEYS


def test_metric_registry_for_registers_only_requested_custom_metrics() -> None:
    """Custom metrics are opt-in per run: present only when a requested id names one.

    The no-request registry must be byte-identical to the default one, so runs
    that never ask for a custom metric keep their Evidence fingerprint.
    """
    from research.aegis_research.metrics import make_metric_registry_for

    frozen = make_metric_registry_for(("ulcer_performance_index",))

    assert "ulcer_performance_index" in frozen
    assert tuple(frozen.extractors) == (
        PORTFOLIO_METRIC_VALUE_KEYS + ("ulcer_performance_index",)
    )
    assert frozen.fingerprint != make_default_metric_registry().fingerprint
    assert (
        make_metric_registry_for(()).fingerprint
        == make_default_metric_registry().fingerprint
    )


def test_metric_registry_for_passes_unknown_ids_through_to_validation() -> None:
    """Unknown ids do not error here; config validation cross-checks fail closed."""
    from research.aegis_research.metrics import make_metric_registry_for

    frozen = make_metric_registry_for(("sharpe_ratio", "not_a_metric"))

    assert frozen.ids() == make_default_metric_registry().ids()


def test_metric_registry_rejects_duplicate_ids() -> None:
    registry = MetricRegistry()
    registry.register(_definition("total_return"), _SPEC)

    with pytest.raises(MetricRegistryError, match="duplicate metric id"):
        registry.register(_definition("total_return"), _SPEC)


def test_metric_registry_rejects_malformed_definition() -> None:
    registry = MetricRegistry()

    with pytest.raises(MetricRegistryError, match="metric id must be non-empty"):
        registry.register(_definition(""), _SPEC)


def test_frozen_metric_registry_definitions_are_immutable() -> None:
    registry = MetricRegistry()
    registry.register(_definition("total_return"), _SPEC)
    frozen = registry.freeze()

    with pytest.raises(TypeError):
        frozen.definitions["sharpe_ratio"] = _definition("sharpe_ratio")  # type: ignore[index]


def test_metric_registry_fingerprint_is_order_independent() -> None:
    first = MetricRegistry()
    first.register(_definition("total_return", title="Total Return"), _SPEC)
    first.register(_definition("sharpe_ratio", title="Sharpe Ratio"), _SPEC)
    second = MetricRegistry()
    second.register(_definition("sharpe_ratio", title="Sharpe Ratio"), _SPEC)
    second.register(_definition("total_return", title="Total Return"), _SPEC)

    assert first.freeze().fingerprint == second.freeze().fingerprint

    changed = MetricRegistry()
    changed.register(_definition("total_return", title="Total Return [%]"), _SPEC)
    changed.register(_definition("sharpe_ratio", title="Sharpe Ratio"), _SPEC)

    assert first.freeze().fingerprint != changed.freeze().fingerprint


def test_fingerprint_is_independent_of_the_extractor() -> None:
    """The extractor carries a callable and must never enter the fingerprint.

    Two registries with identical definitions but different extractors hash the
    same — the fingerprint is a property of the definitions alone.
    """
    one = MetricRegistry()
    one.register(_definition("total_return"), ExtractorSpec(lambda pf, config: None))
    other = MetricRegistry()
    other.register(_definition("total_return"), ExtractorSpec(lambda pf, config: 1.0, scale="percent"))

    assert one.freeze().fingerprint == other.freeze().fingerprint


def test_default_registry_fingerprint_is_byte_stable() -> None:
    """Golden fingerprint: guards against a silent change to the recorded hash.

    The fingerprint flows into Evidence; if a definition field or its
    serialization ever shifts, this pinned value catches it deterministically.
    """
    assert (
        make_default_metric_registry().fingerprint
        == "25995c4bdb5f6c98e4bf62fc60bc38a534e927d2ff469e02102e075d3bdaa3ae"
    )


def test_default_metric_registry_contains_supported_stats() -> None:
    registry = make_default_metric_registry()

    assert set(PORTFOLIO_METRIC_VALUE_KEYS).issubset(registry.ids())
    assert registry.get("total_return").target == "portfolio"


def test_vbt_stats_registration_uses_current_metric_titles() -> None:
    registry = MetricRegistry()

    register_vbt_stats_metrics(
        registry,
        portfolio_metrics={
            "total_return": {"title": "Return From Test"},
            "max_dd": {"title": "Drawdown From Test"},
            "total_trades": {"title": "Trades From Test"},
            "win_rate": {"title": "Win Rate From Test"},
            "total_fees_paid": {"title": "Fees From Test"},
            "sharpe_ratio": {"title": "Sharpe From Test"},
        },
    )

    frozen = registry.freeze()
    assert frozen.get("total_return").title == "Return From Test"


def test_vbt_stats_registration_fails_when_supported_metric_is_missing() -> None:
    registry = MetricRegistry()

    with pytest.raises(MetricRegistryError, match="Portfolio stats metric 'max_dd'"):
        register_vbt_stats_metrics(
            registry,
            portfolio_metrics={
                "total_return": {"title": "Total Return"},
            },
        )


def test_custom_extractor_does_not_leak_across_registries() -> None:
    """A custom metric registered into one registry must not bleed into another.

    The extractor is part of the per-registry record, not process-global state,
    so a custom metric's lifetime is its registry's lifetime — registering it
    here cannot make a freshly built registry compute it.
    """
    from research.aegis_research.metrics.custom import register_custom_metrics

    tainted = MetricRegistry()
    register_vbt_stats_metrics(tainted, portfolio_metrics=_STATS_TITLES)
    register_custom_metrics(
        tainted,
        metrics=[
            (
                MetricDefinition(
                    id="leaked",
                    title="Leaked",
                    source_type="custom",
                    unit="ratio",
                    value_semantics="test",
                ),
                _SPEC,
            )
        ],
    )
    assert "leaked" in tainted.freeze().extractors

    fresh = make_default_metric_registry()
    assert "leaked" not in fresh.extractors


def _definition(metric_id: str, *, title: str = "Total Return") -> MetricDefinition:
    return MetricDefinition(
        id=metric_id,
        title=title,
        source_type=SOURCE_TYPE_VBT_STATS,
        unit="ratio",
        value_semantics="larger_is_better",
        provider="vectorbtpro",
        target="portfolio",
        vbt_metric=metric_id,
        source_method="stats",
    )


def test_builtin_extractors_match_the_portfolio_catalog_exactly() -> None:
    """Pin the one drift direction registration cannot fail-close on.

    A catalog entry without an extractor already fails loudly at registry
    construction (``BUILTIN_EXTRACTORS[metric_id]`` raises KeyError in
    ``register_vbt_stats_metrics``). The reverse is silent: an extractor
    authored in ``BUILTIN_EXTRACTORS`` but never cataloged would never
    register and never compute — dead code. Exact set equality closes it.
    """
    assert set(BUILTIN_EXTRACTORS) == set(PORTFOLIO_METRIC_VALUE_KEYS)


def test_non_finite_metadata_is_normalised_to_null_in_fingerprint() -> None:
    """A NaN metadata value is normalised to null in the fingerprint payload."""
    registry = MetricRegistry()
    definition = MetricDefinition(
        id="nan_metric",
        title="NaN Test",
        source_type=SOURCE_TYPE_VBT_STATS,
        unit="ratio",
        value_semantics="larger_is_better",
        provider="vectorbtpro",
        target="portfolio",
        vbt_metric="nan_metric",
        source_method="stats",
        metadata={"threshold": float("nan")},
    )
    registry.register(definition, _SPEC)
    frozen = registry.freeze()
    # Fingerprint must still be a valid 64-char hex string.
    assert len(frozen.fingerprint) == 64
    assert all(c in "0123456789abcdef" for c in frozen.fingerprint)

    # The NaN was normalised to null in the fingerprint payload.
    payload = definition.fingerprint_payload()
    assert payload["metadata"]["threshold"] is None


def test_non_finite_metadata_fingerprint_is_byte_stable() -> None:
    """Fingerprint is deterministic when NaN metadata is normalised to null."""
    a = MetricRegistry()
    a.register(
        MetricDefinition(
            id="nan",
            title="NaN",
            source_type=SOURCE_TYPE_VBT_STATS,
            unit="ratio",
            value_semantics="larger_is_better",
            metadata={"score": float("nan")},
        ),
        _SPEC,
    )
    b = MetricRegistry()
    b.register(
        MetricDefinition(
            id="nan",
            title="NaN",
            source_type=SOURCE_TYPE_VBT_STATS,
            unit="ratio",
            value_semantics="larger_is_better",
            metadata={"score": float("nan")},
        ),
        _SPEC,
    )
    assert a.freeze().fingerprint == b.freeze().fingerprint
