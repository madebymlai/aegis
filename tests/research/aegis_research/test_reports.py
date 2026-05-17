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


def test_missing_validation_metadata_cannot_survive_by_metrics() -> None:
    report = build_survival_report(
        "missing-validation-metadata",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(),
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    assert "non-decision-grade" in report["reasons"][0]


def test_label_purging_report_requires_split_evidence_even_when_metrics_pass() -> None:
    report = build_survival_report(
        "missing-split-evidence",
        train_metrics=_passing_metrics(),
        test_metrics=_passing_metrics(),
        config=ReportConfig(),
        validation_metadata={
            "decision_grade": True,
            "target": {"split_safety": {"purging_required": True}},
            "split_metadata": {},
        },
    )

    assert report["status"] == REPORT_STATUS_NEEDS_MORE_EVIDENCE
    assert "split evidence" in report["reasons"][0]


def _passing_metrics() -> dict[str, float | int]:
    return {
        "sharpe_ratio": 1.0,
        "max_drawdown_pct": 10.0,
        "total_trades": 10,
    }
