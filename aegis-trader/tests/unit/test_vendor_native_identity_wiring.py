from __future__ import annotations

from pathlib import Path

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.strategy import RebalanceStrategyConfig


def _book() -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("trend"),
                wheel_filename="trend.whl",
                risk_share=1.0,
            ),
        ),
        base_currency="EUR",
    )


def _removed_resolver_name() -> str:
    return "figi" + "_" + "resolver"


def test_rebalance_strategy_config_has_no_removed_resolver_field():
    assert _removed_resolver_name() not in RebalanceStrategyConfig.__struct_fields__


def test_trader_no_longer_ships_removed_resolver_module():
    package_root = Path(__file__).parents[2] / "aegis_trader"

    assert not (package_root / "execution" / f"{_removed_resolver_name()}.py").exists()


def test_rebalance_strategy_config_rejects_removed_resolver_argument():
    try:
        RebalanceStrategyConfig(
            book=_book(), **{_removed_resolver_name(): object()}
        )
    except TypeError:
        return
    raise AssertionError("removed resolver must not be accepted by RebalanceStrategyConfig")
