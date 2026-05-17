from __future__ import annotations

from research.aegis_research.config import REPORT_STATUS_NEEDS_MORE_EVIDENCE, ReportConfig
from research.aegis_research.reports import build_survival_report


def test_non_decision_grade_validation_cannot_survive_by_metrics() -> None:
    report = build_survival_report(
        "diagnostic-run",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(),
        validation_metadata={"decision_grade": False},
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    assert "non-decision-grade" in report["reasons"][0]


def _passing_metrics() -> dict[str, float | int]:
    return {
        "sharpe_ratio": 1.0,
        "max_drawdown_pct": 10.0,
        "total_trades": 10,
    }
