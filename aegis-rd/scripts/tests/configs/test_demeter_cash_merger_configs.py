from __future__ import annotations

from pathlib import Path

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import load_run_config
from research.aegis_research.external_data.sec_cash_mergers import (
    CashMergerEvent,
    CashMergerSnapshot,
)
from research.configs.demeter.cash_merger_family import (
    CashMergerConfigRequest,
    materialize_cash_merger_configs,
)

_ROOT = Path(__file__).resolve().parents[3]


def _snapshot() -> CashMergerSnapshot:
    events = tuple(
        CashMergerEvent(
            target_cik=str(index),
            target_name=f"Target {symbol}",
            target_symbol=symbol,
            status="pending",
            available_at="2025-01-02T00:00:00+00:00",
            offer_price=100.0,
            expected_close=None,
            source_form="8-K",
            source_url=f"https://www.sec.gov/{symbol}",
            accession=str(index),
        )
        for index, symbol in enumerate(("AAA", "BBB", "CCC"), start=1)
    )
    return CashMergerSnapshot(
        events=events,
        source_sha256="abc",
        retrieved_at="2026-01-01T00:00:00+00:00",
        covered_start="2025-01-01",
        covered_end="2026-01-01",
    )


def test_materialized_family_is_six_valid_native_configs_with_preregistered_frontier(
    tmp_path,
) -> None:
    paths = materialize_cash_merger_configs(
        _snapshot(),
        CashMergerConfigRequest(
            event_cache_dir=tmp_path / "events",
            fx_cache_dir=tmp_path / "fx",
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
