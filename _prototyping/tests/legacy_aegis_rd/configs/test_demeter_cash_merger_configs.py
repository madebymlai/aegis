from __future__ import annotations

from pathlib import Path

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import load_run_config
from research.configs.demeter.cash_merger_family import (
    CashMergerConfigRequest,
    materialize_cash_merger_configs,
)

_ROOT = Path(__file__).resolve().parents[3]


def test_materialized_family_is_six_valid_native_configs_with_preregistered_frontier(
    tmp_path,
) -> None:
    paths = materialize_cash_merger_configs(
        CashMergerConfigRequest(
            instrument_ids={"AAA": "AAA.XNAS", "BBB": "BBB.XNYS", "CCC": "CCC.XNAS"},
            benchmark_instrument_id="SPY.ARCA",
            start="2025-01-01",
            end="2026-01-01",
        ),
        tmp_path / "configs",
    )
    registry = discover_component_registry(
        root=_ROOT / "research/components", repo_root=_ROOT
    )

    resolved = [load_run_config(path, component_registry=registry) for path in paths]

    assert [item.config.strategy.params["max_positions"] for item in resolved] == [
        0,
        6,
        8,
        10,
        12,
        12,
    ]
    assert [item.config.strategy.params["residual_entry_enabled"] for item in resolved] == [
        False,
        False,
        False,
        False,
        False,
        True,
    ]
    assert all(
        item.config.strategy.params["max_weight_multiple"] == 1.5 for item in resolved
    )
    assert all("max_name_weight" not in item.config.strategy.params for item in resolved)
    assert all(item.config.portfolio.init_cash == 5_000.0 for item in resolved)
    assert all(item.config.data.instruments[-1] == "SPY.ARCA" for item in resolved)


def test_materialized_family_leaves_external_context_to_indicator_defaults(
    tmp_path,
) -> None:
    paths = materialize_cash_merger_configs(
        CashMergerConfigRequest(
            instrument_ids={"AAA": "AAA.XNAS", "BBB": "BBB.XNYS", "CCC": "CCC.XNAS"},
            benchmark_instrument_id="SPY.ARCA",
            start="2025-01-01",
            end="2026-01-01",
        ),
        tmp_path / "configs",
    )
    registry = discover_component_registry(root=_ROOT / "research/components", repo_root=_ROOT)

    resolved = load_run_config(paths[0], component_registry=registry)
    params = resolved.config.indicators[0].params

    assert "event_snapshot_path" not in params
    assert "fx_snapshot_path" not in params
    assert "event_cache_dir" not in params
    assert "fx_cache_dir" not in params
