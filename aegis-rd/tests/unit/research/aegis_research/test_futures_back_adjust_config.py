"""Config gate for back-adjusted futures (aegis-rd-clz.3).

Adjustments are named to match NautilusTrader's backward ContinuousFutureAdjustmentType
modes: ``backward_ratio`` (multiplicative) and ``backward_spread`` (additive/Panama).
They are accepted only for a source that can supply per-contract data (databento /
``bento`` / ``store``); other sources stay fail-closed, and the legacy ``back_adjust``
spelling is no longer a valid value.
"""

from __future__ import annotations

import pytest

from research.aegis_research.configuration.schema import DataConfig, SymbolSpec


def _future(adjustment: str) -> SymbolSpec:
    return SymbolSpec(ticker="ES", ccy="USD", root="ES", dataset="GLBX.MDP3", adjustment=adjustment)


def _store_future(adjustment: str) -> SymbolSpec:
    return SymbolSpec(root="ES", ccy="USD", dataset="GLBX.MDP3", adjustment=adjustment)


def test_backward_ratio_accepted_for_bento_source() -> None:
    config = DataConfig(
        source="bento",
        arrays=["OHLCV"],
        symbols=[_future("backward_ratio")],
        start="2024-01-01",
        end="2024-12-31",
    )
    assert config.symbols[0].adjustment == "backward_ratio"


def test_backward_spread_accepted_for_store_source() -> None:
    config = DataConfig(
        source="store",
        provider="databento",
        arrays=["OHLCV"],
        symbols=[_store_future("backward_spread")],
        start="2024-01-01",
        end="2024-12-31",
    )
    assert config.symbols[0].adjustment == "backward_spread"


def test_backward_ratio_rejected_for_non_per_contract_source() -> None:
    with pytest.raises(ValueError, match="backward_ratio"):
        DataConfig(
            source="yf",
            arrays=["OHLCV"],
            symbols=[_future("backward_ratio")],
            start="2024-01-01",
            end="2024-12-31",
        )


def test_legacy_back_adjust_spelling_is_rejected() -> None:
    with pytest.raises(ValueError, match="back_adjust"):
        DataConfig(
            source="store",
            provider="databento",
            arrays=["OHLCV"],
            symbols=[_store_future("back_adjust")],
            start="2024-01-01",
            end="2024-12-31",
        )


def _store_dual_config(symbol: SymbolSpec) -> DataConfig:
    return DataConfig(
        source="store",
        provider="databento",
        arrays=["OHLCV"],
        symbols=[symbol],
        start="2024-01-01",
        end="2024-12-31",
    )


def test_pnl_adjustment_carries_a_second_backward_mode_for_a_store_future() -> None:
    # Dual series in one run: signal on backward_ratio, P&L/sizing on backward_spread.
    config = _store_dual_config(
        SymbolSpec(
            root="ES",
            ccy="USD",
            dataset="GLBX.MDP3",
            adjustment="backward_ratio",
            pnl_adjustment="backward_spread",
        )
    )
    assert config.symbols[0].adjustment == "backward_ratio"
    assert config.symbols[0].pnl_adjustment == "backward_spread"


def test_pnl_adjustment_rejected_for_a_listed_symbol() -> None:
    with pytest.raises(ValueError, match="pnl_adjustment"):
        DataConfig(
            source="store",
            provider="yfinance",
            arrays=["OHLCV"],
            symbols=[
                SymbolSpec(
                    ticker="SPY", ccy="USD", figi="BBG000B9XRY4", pnl_adjustment="backward_spread"
                )
            ],
            start="2024-01-01",
            end="2024-12-31",
        )


def test_pnl_adjustment_rejects_an_unknown_mode() -> None:
    with pytest.raises(ValueError, match="pnl_adjustment"):
        _store_dual_config(
            SymbolSpec(
                root="ES",
                ccy="USD",
                dataset="GLBX.MDP3",
                adjustment="backward_ratio",
                pnl_adjustment="panama",
            )
        )
