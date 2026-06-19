"""Config gate for back-adjusted futures (aegis-rd-clz.3).

``adjustment: back_adjust`` is accepted only for a source that can supply
per-contract data (databento / ``bento``); other sources stay fail-closed.
"""

from __future__ import annotations

import pytest

from research.aegis_research.configuration.schema import DataConfig, SymbolSpec


def _future(adjustment: str) -> SymbolSpec:
    return SymbolSpec(ticker="ES", ccy="USD", root="ES", dataset="GLBX.MDP3", adjustment=adjustment)


def test_back_adjust_accepted_for_bento_source() -> None:
    config = DataConfig(
        source="bento",
        arrays=["OHLCV"],
        symbols=[_future("back_adjust")],
        start="2024-01-01",
        end="2024-12-31",
    )
    assert config.symbols[0].adjustment == "back_adjust"


def test_back_adjust_rejected_for_non_per_contract_source() -> None:
    with pytest.raises(ValueError, match="back_adjust"):
        DataConfig(source="yf", arrays=["OHLCV"], symbols=[_future("back_adjust")])
