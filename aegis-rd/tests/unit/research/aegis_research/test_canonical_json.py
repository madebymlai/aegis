from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from research.aegis_research import configuration as public_config
from research.aegis_research.canonical_json import canonical_json_bytes, to_builtin
from research.aegis_research.metrics import ResolvedMetrics, make_default_metric_registry
from tests.support.research.aegis_research.factories import (
    make_portfolio_config,
    make_ranking_config,
    make_run_config,
    make_run_source_ref_config,
)


@dataclass(frozen=True)
class _NestedPayload:
    enabled: bool
    threshold: np.float64


@dataclass(frozen=True)
class _CanonicalPayload:
    name: str
    nested: _NestedPayload
    values: tuple[object, ...]


def test_to_builtin_is_shared_canonical_dataclass_converter() -> None:
    payload = _CanonicalPayload(
        name="demo",
        nested=_NestedPayload(enabled=True, threshold=np.float64(0.25)),
        values=("alpha", np.int64(3)),
    )

    assert public_config.to_builtin is to_builtin
    assert to_builtin(payload) == {
        "name": "demo",
        "nested": {"enabled": True, "threshold": 0.25},
        "values": ["alpha", 3],
    }
    assert canonical_json_bytes(payload) == (
        b'{"name":"demo","nested":{"enabled":true,"threshold":0.25},"values":["alpha",3]}'
    )


def test_to_builtin_serializes_resolved_run_config_wrapped_config() -> None:
    run_config = make_run_config(
        name="demo",
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[],
        ranking=make_ranking_config(metric="sharpe_ratio"),
        portfolio=make_portfolio_config(direction="longonly"),
    )
    wrapper = public_config.ResolvedRunConfig(
        config=run_config,
        raw_config_hash="hash",
        authored_config={},
        metrics=ResolvedMetrics.resolve(make_default_metric_registry(), "sharpe_ratio"),
    )

    assert to_builtin(wrapper) == to_builtin(run_config)
