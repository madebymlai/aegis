"""Pipeline setup stage.

Resolves component locks, builds the optimization source and
evidence baseline for the strategy sweep.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
)
from research.aegis_research.config import (
    RunConfig,
    to_builtin,
)
from research.aegis_research.data import (
    MarketDataBundle,
    MarketDataResult,
)
from research.aegis_research.data_arrays import (
    DataArrayContract,
)
from research.aegis_research.optimization.candidate_publishing import (
    candidate_store_path,
)
from research.aegis_research.optimization.component_source import (
    build_component_optimization_source,
)
from research.aegis_research.optimization.evidence_ledger import (
    OPTIMIZATION_ROUTE_SCHEMA_VERSION,
    RunEvidence,
)
from research.aegis_research.optimization.lock_resolution import (
    resolve_component_locks,
)
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_evidence_payload,
)
from research.aegis_research.optimization.source import (
    OPTIMIZATION_SOURCE_CONTRACT,
)
from research.aegis_research.run_splits import build_run_splits_result


def run_pipeline_setup(
    *,
    config: RunConfig,
    component_registry: FrozenComponentRegistry,
    data: MarketDataBundle,
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    run_evidence: RunEvidence,
) -> dict[str, Any]:
    """Resolve locks, build the optimization source, and construct the evidence baseline.

    Returns a dict with keys:
        store_path, resolved_component_params, resolved_locks,
        optimization_source, strategy_evidence, close, split_result,
        optimization_builtin, portfolio_builtin.
    """
    store_path = candidate_store_path(config)
    resolved_component_params, resolved_locks = resolve_component_locks(
        config,
        candidate_store_path=store_path,
    )
    optimization_source = build_component_optimization_source(
        config,
        component_registry=component_registry,
        data=data,
        resolved_component_params=resolved_component_params,
    )
    strategy_evidence = optimization_source.evidence["strategy"]
    close = data.feature("Close")
    open_ = data.feature("Open")
    split_result = build_run_splits_result(close.index, config.optimization.split)
    optimization_builtin = to_builtin(config.optimization)
    portfolio_builtin = to_builtin(config.portfolio)
    run_evidence.initialize_optimization(
        _optimization_evidence_baseline(
            optimization_source=optimization_source,
            optimization_builtin=optimization_builtin,
            split_metadata=split_result.metadata,
            data_result=data_result,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry_fingerprint,
            resolved_locks=resolved_locks,
        )
    )
    return {
        "store_path": store_path,
        "resolved_component_params": resolved_component_params,
        "resolved_locks": resolved_locks,
        "optimization_source": optimization_source,
        "strategy_evidence": strategy_evidence,
        "close": close,
        "open_": open_,
        "split_result": split_result,
        "optimization_builtin": optimization_builtin,
        "portfolio_builtin": portfolio_builtin,
    }


def _optimization_evidence_baseline(
    *,
    optimization_source: Any,
    optimization_builtin: Mapping[str, Any],
    split_metadata: Mapping[str, Any],
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    resolved_locks: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": OPTIMIZATION_ROUTE_SCHEMA_VERSION,
        "contract": OPTIMIZATION_SOURCE_CONTRACT,
        "source": optimization_source.evidence,
        "param_names": list(optimization_source.params),
        "optimization": optimization_builtin,
        "split": split_metadata,
        "data": build_run_data_evidence_payload(data_result, array_contract),
        "metric_registry_fingerprint": metric_registry_fingerprint,
        "open_prices_available": True,
        "resolved_locks": resolved_locks,
    }
