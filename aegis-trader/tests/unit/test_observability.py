"""Unit tests for the ObservabilityPort — pure domain, zero Nautilus."""

from __future__ import annotations

import pytest

from aegis_trader.observability.port import (
    ObservabilityPort,
    RebalanceSummary,
    GateOutcome,
)


def _make_summary(**overrides) -> RebalanceSummary:
    defaults = dict(
        nav=100_000.0,
        num_sleeves=2,
        num_targets=3,
        num_orders=2,
        num_quarantined=1,
        quarantined_figis=("FIGI_ORPHAN",),
        gate_outcome=GateOutcome.PASS,
        total_notional=22_000.0,
    )
    defaults.update(overrides)
    return RebalanceSummary(**defaults)


class _FakePort(ObservabilityPort):
    """Fake implementation that records calls for testing."""

    def __init__(self) -> None:
        self.rebalance_logs: list[RebalanceSummary] = []
        self.quarantine_alerts: list[tuple[str, ...]] = []
        self.halt_alerts: list[str] = []
        self.info_logs: list[str] = []
        self.warning_logs: list[str] = []
        self.error_logs: list[str] = []

    def log_rebalance_decision(self, summary: RebalanceSummary) -> None:
        self.rebalance_logs.append(summary)

    def alert_quarantine(self, figis: tuple[str, ...]) -> None:
        self.quarantine_alerts.append(figis)

    def alert_halt(self, reason: str) -> None:
        self.halt_alerts.append(reason)

    def log_info(self, message: str) -> None:
        self.info_logs.append(message)

    def log_warning(self, message: str) -> None:
        self.warning_logs.append(message)

    def log_error(self, message: str) -> None:
        self.error_logs.append(message)


class TestRebalanceSummary:
    """RebalanceSummary value type."""

    def test_construction(self):
        summary = _make_summary()
        assert summary.nav == 100_000.0
        assert summary.num_sleeves == 2
        assert summary.num_orders == 2
        assert summary.gate_outcome == GateOutcome.PASS

    def test_gate_outcome_enum(self):
        assert GateOutcome.PASS.value == "pass"
        assert GateOutcome.HALT.value == "halt"
        assert GateOutcome.ERROR.value == "error"


class TestObservabilityPort:
    """ObservabilityPort protocol with fake implementation."""

    def test_log_rebalance_decision(self):
        port = _FakePort()
        summary = _make_summary()
        port.log_rebalance_decision(summary)
        assert len(port.rebalance_logs) == 1
        assert port.rebalance_logs[0] is summary

    def test_alert_quarantine(self):
        port = _FakePort()
        figis = ("FIGI_A", "FIGI_B")
        port.alert_quarantine(figis)
        assert port.quarantine_alerts == [figis]

    def test_alert_halt(self):
        port = _FakePort()
        port.alert_halt("NAV mismatch")
        assert port.halt_alerts == ["NAV mismatch"]

    def test_multiple_rebalances(self):
        port = _FakePort()
        s1 = _make_summary(num_orders=1)
        s2 = _make_summary(num_orders=3)
        port.log_rebalance_decision(s1)
        port.log_rebalance_decision(s2)
        assert len(port.rebalance_logs) == 2
        assert port.rebalance_logs[0].num_orders == 1
        assert port.rebalance_logs[1].num_orders == 3

    def test_empty_quarantine(self):
        port = _FakePort()
        port.alert_quarantine(())
        assert port.quarantine_alerts == [()]
