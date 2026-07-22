"""Acceptance tests for the migrated sample lock configs (aegis-rd-396.2).

The two sample configs ``etf_vanguard_tune_lock_mom.yaml`` and
``etf_vanguard_tune_lock_vol.yaml`` historically froze one Indicator via a
per-Component ``lock_id`` while the Strategy and the other Indicators optimized.
ADR-0006 removes per-Component lock tokens, so partial freeze must now be
expressed as inline values-only ``params:`` on the frozen Component.

These fixtures live in the tracked ``tests/fixtures`` tree (decoupled with
``tests.*`` Component ids), so the tests always run and pin the migrated
contract end to end: each config loads and validates, carries no per-Component
lock reference, inlines the previously-frozen Component's literal params, and
the optimization source freezes exactly that Component (``param_mode ==
"fixed"``) while every other Component keeps optimizing (``param_mode ==
"parameterized"``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from aegis_runtime import MarketDataBundle
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import load_run_config
from research.aegis_research.optimization.component_source import (
    build_component_optimization_source,
)

_CONFIG_DIR = Path("tests/fixtures/configs")

# The literal parameter values each config's previously-frozen Indicator
# resolved to under the old per-Component lock, read once from the candidate
# store / locked-run manifest while that resolution path still existed.
_FROZEN = {
    "tests_tune_lock_mom.yaml": (
        "tests.momentum_score",
        {"h1": 15, "h2": 42, "h3": 100, "h4": 200, "w1": 8.0, "w2": 4.0, "w3": 3.0, "w4": 2.0},
    ),
    "tests_tune_lock_vol.yaml": (
        "tests.realized_vol",
        {"window": 16},
    ),
}

_LOCK_REF_FIELDS = ("lock_id", "candidate_id", "run_id")


def _config_path(name: str) -> Path:
    return _CONFIG_DIR / name


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _market_data_bundle() -> MarketDataBundle:
    index = pd.date_range("2020-01-01", periods=400, freq="D")
    columns = [
        _id("SPY.XNAS"),
        _id("IWM.XNAS"),
        _id("EEM.XNAS"),
        _id("TLT.XNAS"),
        _id("GLD.XNAS"),
        _id("DBC.XNAS"),
        _id("VNQ.XNAS"),
        _id("UUP.XNAS"),
        _id("XLE.XNAS"),
        _id("XLU.XNAS"),
    ]
    rng = np.random.default_rng(0)
    frame = pd.DataFrame(
        100 + np.cumsum(rng.normal(size=(len(index), len(columns))), axis=0),
        index=index,
        columns=columns,
    )
    arrays = {name: frame.copy() for name in ("Open", "High", "Low", "Close", "Volume")}
    return MarketDataBundle(arrays=arrays)


@pytest.fixture(scope="module")
def registry():
    return discover_component_registry(root="tests/fixtures/components")


@pytest.mark.parametrize("config_name", sorted(_FROZEN))
def test_sample_lock_config_loads_and_validates(config_name: str, registry) -> None:
    resolved = load_run_config(_config_path(config_name), component_registry=registry)
    assert resolved.config.name == config_name.removesuffix(".yaml")


@pytest.mark.parametrize("config_name", sorted(_FROZEN))
def test_sample_lock_config_has_no_per_component_lock_reference(config_name: str, registry) -> None:
    # ADR-0006 (aegis-rd-396.4): the per-Component lock reference surface is gone from
    # the schema entirely — so the migrated configs cannot carry one.
    config = load_run_config(_config_path(config_name), component_registry=registry).config
    refs = (config.strategy, *config.indicators)
    for ref in refs:
        for field in _LOCK_REF_FIELDS:
            assert not hasattr(ref, field), (
                f"{config_name}: {ref.id} still exposes per-Component {field}"
            )


@pytest.mark.parametrize("config_name", sorted(_FROZEN))
def test_sample_lock_config_inlines_frozen_component_params(config_name: str, registry) -> None:
    frozen_id, frozen_params = _FROZEN[config_name]
    config = load_run_config(_config_path(config_name), component_registry=registry).config
    frozen = next(ref for ref in config.indicators if ref.id == frozen_id)
    assert frozen.params == frozen_params
    other = next(ref for ref in config.indicators if ref.id != frozen_id)
    assert other.params == {}


@pytest.mark.parametrize("config_name", sorted(_FROZEN))
def test_sample_lock_config_freezes_only_the_previously_locked_component(
    config_name: str, registry
) -> None:
    frozen_id, _ = _FROZEN[config_name]
    config = load_run_config(_config_path(config_name), component_registry=registry).config
    source = build_component_optimization_source(
        config,
        component_registry=registry,
        data=_market_data_bundle(),
    )
    modes = {ind["id"]: ind["param_mode"] for ind in source.evidence["indicators"]}
    modes[source.evidence["strategy"]["id"]] = source.evidence["strategy"]["param_mode"]
    assert modes[frozen_id] == "fixed"
    for component_id, mode in modes.items():
        if component_id == frozen_id:
            continue
        assert mode == "parameterized", f"{config_name}: {component_id} should keep optimizing"
