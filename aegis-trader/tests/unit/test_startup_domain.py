"""Unit tests for startup halt value objects."""

from __future__ import annotations

import aegis_trader.trader.pipeline as pipeline
from aegis_trader.domain.startup import StartupGate, StartupResult


def test_startup_result_halts_when_trading_is_disabled() -> None:
    result = StartupResult(
        trading_enabled=False,
        halt_gate=StartupGate.ACCOUNT_INTEGRITY,
        halt_reason="cash mismatch",
    )

    should_halt = result.should_halt

    assert should_halt is True


def test_pipeline_does_not_reexport_startup_gate() -> None:
    exports_startup_gate = hasattr(pipeline, "StartupGate")

    assert exports_startup_gate is False


def test_pipeline_does_not_reexport_startup_result() -> None:
    exports_startup_result = hasattr(pipeline, "StartupResult")

    assert exports_startup_result is False
