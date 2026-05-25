from __future__ import annotations

import pytest
from vectorbtpro import vbt

from research.aegis_research.optimization.source import (
    OPTIMIZATION_SOURCE_CONTRACT,
    OPTIMIZATION_SOURCE_KIND,
    OptimizationSourceError,
    validate_optimization_source,
)


def test_optimization_source_contract_accepts_vbt_params_and_pipeline() -> None:
    def pipeline(data, rsi_window, ma_window, entry_threshold, exit_threshold):
        return data, rsi_window, ma_window, entry_threshold, exit_threshold

    source = validate_optimization_source(
        {
            "contract": OPTIMIZATION_SOURCE_CONTRACT,
            "kind": OPTIMIZATION_SOURCE_KIND,
            "pipeline": pipeline,
            "params": {
                "rsi_window": vbt.Param([7, 14]),
                "ma_window": vbt.Param([50, 100]),
                "entry_threshold": vbt.Param([40.0, 45.0], level=0),
                "exit_threshold": vbt.Param([60.0, 55.0], level=0),
            },
            "output_name": "active",
            "diagnostics": {"fixture": True},
        },
        source_evidence={"source": "component", "id": "native_rsi"},
    )

    assert source.pipeline is pipeline
    assert source.params["rsi_window"].value == [7, 14]
    assert source.params["entry_threshold"].level == 0
    assert source.params["exit_threshold"].level == 0
    assert source.evidence == {"source": "component", "id": "native_rsi"}
    assert source.diagnostics == {"fixture": True}


def test_optimization_source_contract_accepts_vbt_condition_params() -> None:
    def pipeline(data, fast_window, slow_window):
        return data, fast_window, slow_window

    source = validate_optimization_source(
        {
            "contract": OPTIMIZATION_SOURCE_CONTRACT,
            "kind": OPTIMIZATION_SOURCE_KIND,
            "pipeline": pipeline,
            "params": {
                "fast_window": vbt.Param([5, 10], condition="fast_window < slow_window"),
                "slow_window": vbt.Param([20, 50]),
            },
            "output_name": "active",
        },
        source_evidence={"source": "component", "id": "native_ma"},
    )

    assert source.params["fast_window"].condition == "fast_window < slow_window"


@pytest.mark.parametrize("forbidden_key", ["metrics", "metric_source", "portfolio", "candidate_axis"])
def test_optimization_source_contract_rejects_authoritative_metrics_or_candidate_axes(
    forbidden_key: str,
) -> None:
    def pipeline(data, window):
        return data, window

    result = {
        "contract": OPTIMIZATION_SOURCE_CONTRACT,
        "kind": OPTIMIZATION_SOURCE_KIND,
        "pipeline": pipeline,
        "params": {"window": vbt.Param([2, 3])},
        forbidden_key: {},
    }

    with pytest.raises(OptimizationSourceError) as error:
        validate_optimization_source(result, source_evidence={"id": "bad"})

    assert forbidden_key in str(error.value)


def test_optimization_source_contract_rejects_legacy_playbook_sweep_shape() -> None:
    with pytest.raises(OptimizationSourceError) as error:
        validate_optimization_source(
            {
                "contract": "aegis.playbook_sweep.v1",
                "kind": "strategy_axis",
                "candidate_axis": [],
                "materialize_signals": lambda request: request,
            },
            source_evidence={"source": "playbook", "id": "legacy"},
        )

    assert OPTIMIZATION_SOURCE_CONTRACT in str(error.value)


def test_optimization_source_rejects_hidden_vbt_params() -> None:
    def pipeline(data, fast_window, slow_window):
        return data, fast_window, slow_window

    with pytest.raises(OptimizationSourceError, match="hide=True"):
        validate_optimization_source(
            {
                "contract": OPTIMIZATION_SOURCE_CONTRACT,
                "kind": OPTIMIZATION_SOURCE_KIND,
                "pipeline": pipeline,
                "params": {
                    "fast_window": vbt.Param([2, 5]),
                    "slow_window": vbt.Param([10, 20], hide=True),
                },
            },
            source_evidence={"source": "test"},
        )


@pytest.mark.parametrize("param_name", ["split", "set", "symbol", "metric_name"])
def test_optimization_source_rejects_reserved_result_coordinate_param_names(
    param_name: str,
) -> None:
    def pipeline(data, **params):
        return data, params

    with pytest.raises(OptimizationSourceError, match="reserved"):
        validate_optimization_source(
            {
                "contract": OPTIMIZATION_SOURCE_CONTRACT,
                "kind": OPTIMIZATION_SOURCE_KIND,
                "pipeline": pipeline,
                "params": {param_name: vbt.Param([1, 2])},
            },
            source_evidence={"source": "test"},
        )
