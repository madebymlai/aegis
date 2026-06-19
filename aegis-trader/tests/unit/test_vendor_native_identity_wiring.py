from __future__ import annotations

from pathlib import Path

import pytest

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


REMOVED_RESOLVER_FIELD = "figi" + "_" + "resolver"


def test_rebalance_strategy_config_has_no_removed_resolver_field():
    assert REMOVED_RESOLVER_FIELD not in RebalanceStrategyConfig.__struct_fields__


def test_trader_no_longer_ships_removed_resolver_module():
    package_root = Path(__file__).parents[2] / "aegis_trader"

    assert not (package_root / "execution" / f"{REMOVED_RESOLVER_FIELD}.py").exists()


def test_rebalance_strategy_config_rejects_removed_resolver_argument():
    with pytest.raises(TypeError):
        RebalanceStrategyConfig(book=_book(), **{REMOVED_RESOLVER_FIELD: object()})
