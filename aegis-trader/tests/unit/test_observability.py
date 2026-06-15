"""Unit tests for the ObservabilityPort — pure domain, zero Nautilus."""

from __future__ import annotations

from aegis_trader.observability.port import (
    GateOutcome,
    ObservabilityPort,
    RebalanceSummary,
)


def _make_summary(
    *,
    nav: float = 100_000.0,
    num_sleeves: int = 2,
    num_targets: int = 3,
    num_orders: int = 2,
    gate_outcome: GateOutcome = GateOutcome.PASS,
    total_notional: float = 22_000.0,
) -> RebalanceSummary:
    return RebalanceSummary(
        nav=nav,
        num_sleeves=num_sleeves,
        num_targets=num_targets,
        num_orders=num_orders,
        gate_outcome=gate_outcome,
        total_notional=total_notional,
    )


class _FakePort(ObservabilityPort):
    """Fake implementation that records calls for testing."""

    def __init__(self) -> None:
        self.rebalance_logs: list[RebalanceSummary] = []
        self.halt_alerts: list[str] = []

    def log_rebalance_decision(self, summary: RebalanceSummary) -> None:
        self.rebalance_logs.append(summary)

    def alert_halt(self, reason: str) -> None:
        self.halt_alerts.append(reason)


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
