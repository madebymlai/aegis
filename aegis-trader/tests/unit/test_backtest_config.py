"""Backtest engine config assertions."""

from __future__ import annotations

from nautilus_trader.risk.config import RiskEngineConfig

from aegis_trader.backtest import build_backtest_engine_config


def test_backtest_engine_config_uses_nautilus_risk_defaults():
    """Pin the upstream defaults Aegis relies on without configuring them."""
    cfg = build_backtest_engine_config()
    risk = cfg.risk_engine

    assert type(risk) is RiskEngineConfig
    assert risk.bypass is False
    assert risk.max_order_submit_rate == "100/00:00:01"
    assert risk.max_order_modify_rate == "100/00:00:01"


def test_backtest_engine_config_accepts_bar_capacity_for_cache_window():
    cfg = build_backtest_engine_config(bar_capacity=64)
    assert cfg.cache is not None
    assert cfg.cache.bar_capacity == 64
