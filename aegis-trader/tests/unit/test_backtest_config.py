"""Backtest engine + RiskEngine config assertions.

Absorbed into the backtest module from the dissolved ``trader/modes.py``
(aegis-rd-r8b.8): the backtest RiskEngine mirrors the live node's wiring so the
overlay is constructed the same way it trades — "what you backtest is what you
trade".
"""

from __future__ import annotations

from aegis_trader.backtest import build_backtest_engine_config, build_risk_engine_config


def test_risk_engine_config_carries_rate_limits_and_is_not_bypassed():
    cfg = build_risk_engine_config()
    assert cfg.bypass is False
    assert cfg.max_order_submit_rate == "10/00:00:01"
    assert cfg.max_order_modify_rate == "10/00:00:01"


def test_backtest_engine_config_mirrors_risk_wiring():
    cfg = build_backtest_engine_config()
    assert cfg.risk_engine is not None
    assert cfg.risk_engine.bypass is False
    assert cfg.risk_engine.max_order_submit_rate == "10/00:00:01"


def test_backtest_engine_config_accepts_bar_capacity_for_cache_window():
    cfg = build_backtest_engine_config(bar_capacity=64)
    assert cfg.cache is not None
    assert cfg.cache.bar_capacity == 64
