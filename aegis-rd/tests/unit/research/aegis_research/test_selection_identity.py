from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.metrics import ResolvedMetrics, make_default_metric_registry
from research.aegis_research.optimization.observation_blocks import (
    ObservationBlockAnalysis,
    ObservationBlocks,
)
from research.aegis_research.optimization.precompute import empty_precompute
from research.aegis_research.optimization.preflight import OptimizationPreflight, build_preflight
from research.aegis_research.optimization.selection_identity import build_selection_identity
from research.aegis_research.optimization.source import OptimizationSource
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_report_config,
)


def _selection_inputs() -> tuple[
    ObservationBlockAnalysis,
    OptimizationPreflight,
    ResolvedMetrics,
    Any,
]:
    def should_not_execute(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("preflight must not execute the source")

    source = OptimizationSource(
        precompute=empty_precompute,
        simulate=should_not_execute,
        resolve_lookbacks=lambda params: {"component": int(params["window"])},
        params={"window": vbt.Param([2, 4])},
        identity={"source": "identity-oracle"},
    )
    optimization = make_optimization_config(
        search="grid",
        observation_block_bars=3,
        seed=7,
    )
    preflight = build_preflight(
        source=source,
        optimization=optimization,
        index=pd.date_range("2024-01-01", periods=12, freq="D"),
        symbol_count=1,
        metric_count=1,
        has_open_prices=True,
    )
    registry = make_default_metric_registry()
    analysis = cast(
        ObservationBlockAnalysis,
        SimpleNamespace(blocks=preflight.blocks),
    )
    return (
        analysis,
        preflight,
        ResolvedMetrics.resolve(registry, "total_return"),
        optimization,
    )


def test_resolved_metrics_preserve_selection_identity_bytes() -> None:
    analysis, preflight, metrics, optimization = _selection_inputs()

    identity = build_selection_identity(
        analysis=analysis,
        preflight=preflight,
        optimization=optimization,
        metrics=metrics,
        min_trades=3,
        report=make_report_config(),
        direction="longonly",
        fill_timing="next_close",
        data_start="2024-01-01",
    )

    payload = canonical_json_bytes(identity)
    assert len(payload) == 3773
    assert sha256(payload).hexdigest() == (
        "f6fc25bf96b78c7f3fb6670af778d9572b84f349f1d2d7a3be83b53f6c14016f"
    )


def test_selection_identity_still_requires_executed_preflight_blocks() -> None:
    _, preflight, metrics, optimization = _selection_inputs()
    mismatched_analysis = cast(
        ObservationBlockAnalysis,
        SimpleNamespace(
            blocks=ObservationBlocks.from_bounds(
                preflight.blocks.index,
                [(4, 8), (8, 12)],
            )
        ),
    )

    with pytest.raises(
        ValueError,
        match="execution Observation Blocks must equal preflighted blocks",
    ):
        build_selection_identity(
            analysis=mismatched_analysis,
            preflight=preflight,
            optimization=optimization,
            metrics=metrics,
            min_trades=3,
            report=make_report_config(),
            direction="longonly",
            fill_timing="next_close",
            data_start="2024-01-01",
        )
