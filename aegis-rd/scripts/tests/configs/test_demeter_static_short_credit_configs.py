from pathlib import Path

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import load_run_config

_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_ROOT = _ROOT / "research/configs/demeter"


def _load(name: str):
    registry = discover_component_registry(
        root=_ROOT / "research/components",
        repo_root=_ROOT,
    )
    return load_run_config(_CONFIG_ROOT / name, component_registry=registry)


def _assert_static_baseline_contract(resolved) -> None:
    config = resolved.config
    assert config.data.start == "2020-08-10"
    assert config.strategy.id == "demeter.static_short_credit"
    assert config.strategy.params == {}
    assert config.indicators == []
    assert config.portfolio.gross_cap == 1.0
    assert config.portfolio.net_cap == 1.0
    assert config.portfolio.fixed_fee == 3.75
    assert config.portfolio.fees == 0.0
    assert config.portfolio.slippage == 0.0005


def test_static_short_credit_config_uses_the_qualified_eur_hedged_pair() -> None:
    hedged = _load("static_short_credit_hedged.yaml")

    assert hedged.config.data.instruments == ["CBUS5E.XBRU", "STEA.LSEETF"]
    assert hedged.config.data.mark_modes == {"CBUS5E.XBRU": "QUOTE"}
    assert hedged.config.data.end == "2026-07-11"
    _assert_static_baseline_contract(hedged)


def test_unhedged_control_matches_the_hedged_execution_contract() -> None:
    hedged = _load("static_short_credit_hedged.yaml")
    unhedged = _load("static_short_credit_unhedged.yaml")

    assert unhedged.config.data.instruments == ["SDIG.LSEETF", "SDHY.LSEETF"]
    assert unhedged.config.data.mark_modes == {}
    assert unhedged.config.portfolio == hedged.config.portfolio
    assert unhedged.config.data.end == "2026-07-01"
    _assert_static_baseline_contract(unhedged)


def test_accumulating_stea_config_declares_no_synthetic_income_input() -> None:
    resolved = _load("static_short_credit_hedged.yaml")
    authored = resolved.authored_config_document()

    assert authored["data"]["arrays"] == ["OHLCV"]
    assert authored["indicators"] == []
    assert "distribution" not in str(authored).lower()
    assert "fred" not in str(authored).lower()


def test_duration_comparator_uses_the_four_qualified_eur_hedged_contracts() -> None:
    baseline = _load("static_short_credit_hedged.yaml")
    comparator = _load("static_credit_duration_comparator.yaml")

    assert comparator.config.data.instruments == [
        "CBUS5E.XBRU",
        "LQEE.LSEETF",
        "STEA.LSEETF",
        "IHYE.LSEETF",
    ]
    assert comparator.config.data.mark_modes == {"CBUS5E.XBRU": "QUOTE"}
    assert comparator.config.portfolio == baseline.config.portfolio
    assert comparator.config.optimization == baseline.config.optimization
    assert comparator.config.data.end == "2026-07-01"
    _assert_static_baseline_contract(comparator)

    authored = comparator.authored_config_document()
    assert authored["data"]["arrays"] == ["OHLCV"]
    assert authored["indicators"] == []
    assert authored["strategy"] == {"id": "demeter.static_short_credit"}
    assert "fred" not in str(authored).lower()
