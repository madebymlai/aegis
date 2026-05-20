from __future__ import annotations

import json
import math
import warnings
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from research.aegis_research.config import (
    REPORT_STATUS_NEEDS_MORE_EVIDENCE,
    REPORT_STATUS_REJECTED,
    REPORT_STATUS_SURVIVED,
    ReportConfig,
    to_builtin,
)
from research.aegis_research.splits import split_purging_passed

PORTFOLIO_METRIC_SCOPE = "shared_cash_group"
METRICS_SCHEMA_VERSION = "metrics.v3"
METRIC_AVAILABILITY_AVAILABLE = "available"
METRIC_AVAILABILITY_UNAVAILABLE = "unavailable_metric"
METRIC_AVAILABILITY_NOT_CONFIGURED = "not_configured"
GATE_STATUS_PASS = "pass"
GATE_STATUS_FAIL = "fail"
GATE_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
GATE_STATUS_UNAVAILABLE_METRIC = "unavailable_metric"
GATE_STATUS_INVALID_VALIDATION = "invalid_validation"
METRIC_VALUE_KEYS = (
    "total_return_pct",
    "sharpe_ratio",
    "max_drawdown_pct",
    "total_trades",
    "win_rate_pct",
    "total_fees_paid",
)
PORTFOLIO_METRIC_CATALOG: dict[str, dict[str, Any]] = {
    "total_return_pct": {
        "vbt_metric": "total_return",
        "unit": "percent",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": False,
    },
    "max_drawdown_pct": {
        "vbt_metric": "max_dd",
        "unit": "percent_loss_magnitude",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": True,
    },
    "total_trades": {
        "vbt_metric": "total_trades",
        "unit": "count",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": True,
    },
    "win_rate_pct": {
        "vbt_metric": "win_rate",
        "unit": "percent",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": False,
    },
    "total_fees_paid": {
        "vbt_metric": "total_fees_paid",
        "unit": "cash",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": False,
    },
    "sharpe_ratio": {
        "vbt_metric": "sharpe_ratio",
        "unit": "ratio",
        "source_method": "get_sharpe_ratio",
        "required_report_output": True,
        "required_gate_input": True,
    },
}
PORTFOLIO_STATS_METRICS = tuple(
    metric["vbt_metric"]
    for metric in PORTFOLIO_METRIC_CATALOG.values()
    if metric["source_method"] == "stats"
)
OPTIONAL_DIAGNOSTICS = {
    "probabilistic_sharpe_ratio": {
        "method": "get_prob_sharpe_ratio",
        "unit": "probability",
        "vbt_metric": "prob_sharpe_ratio",
    },
    "deflated_sharpe_ratio": {
        "method": "get_deflated_sharpe_ratio",
        "unit": "ratio",
        "vbt_metric": "deflated_sharpe_ratio",
    },
}


def portfolio_metrics(pf: Any, config: ReportConfig) -> dict[str, Any]:
    sharpe_kwargs = {
        "freq": pd.Timedelta(config.freq),
        "year_freq": pd.Timedelta(config.year_freq),
    }
    evidence_settings = portfolio_metric_assumptions(config)
    stats, stats_warnings = _capture_warnings(
        lambda: pf.stats(metrics=list(PORTFOLIO_STATS_METRICS), agg_func=None)
    )
    per_symbol_stats, per_symbol_stats_warnings = _capture_warnings(
        lambda: pf.stats(
            metrics=list(PORTFOLIO_STATS_METRICS),
            agg_func=None,
            group_by=False,
        )
    )
    sharpe_ratio, sharpe_warnings = _capture_warnings(lambda: pf.get_sharpe_ratio(**sharpe_kwargs))
    per_symbol_sharpe, per_symbol_sharpe_warnings = _capture_warnings(
        lambda: pf.get_sharpe_ratio(
            **sharpe_kwargs,
            group_by=False,
        )
    )

    metrics: dict[str, Any] = {}
    metric_evidence: dict[str, Any] = {}
    per_symbol: dict[str, dict[str, Any]] = {}
    per_symbol_metric_evidence: dict[str, dict[str, Any]] = {}
    for metric_name, metric in PORTFOLIO_METRIC_CATALOG.items():
        vbt_metric = _vbt_metric_config(pf, metric["vbt_metric"])
        title = vbt_metric["title"]
        source = _metric_source(metric, title)
        if metric["source_method"] == "stats":
            raw_value = _headline_raw_metric(stats, title)
            raw_symbol_values = _raw_metric_map(per_symbol_stats, title)
            warnings_for_metric = stats_warnings
            per_symbol_warnings = per_symbol_stats_warnings
        else:
            raw_value = _headline_raw_value(sharpe_ratio)
            raw_symbol_values = _raw_value_map(per_symbol_sharpe)
            warnings_for_metric = sharpe_warnings
            per_symbol_warnings = per_symbol_sharpe_warnings

        evidence = _metric_evidence(
            metric_name,
            metric,
            source,
            raw_value,
            settings=evidence_settings,
            warning_records=warnings_for_metric,
        )
        symbol_evidence = {
            symbol: _metric_evidence(
                metric_name,
                metric,
                source,
                value,
                settings=evidence_settings,
                warning_records=per_symbol_warnings,
            )
            for symbol, value in raw_symbol_values.items()
        }
        metrics[metric_name] = evidence["value"]
        metric_evidence[metric_name] = evidence
        per_symbol[metric_name] = {
            symbol: evidence["value"] for symbol, evidence in symbol_evidence.items()
        }
        per_symbol_metric_evidence[metric_name] = symbol_evidence

    return {
        **metrics,
        "metric_scope": PORTFOLIO_METRIC_SCOPE,
        "metric_assumptions": evidence_settings,
        "metric_evidence": metric_evidence,
        "metric_roles": _metric_roles(),
        "optional_diagnostics": _optional_diagnostics(pf, sharpe_kwargs, evidence_settings),
        "per_symbol": per_symbol,
        "per_symbol_metric_evidence": per_symbol_metric_evidence,
    }


def portfolio_metrics_by_candidate_group(
    pf: Any,
    config: ReportConfig,
    candidate_ids: Iterable[str],
) -> dict[str, dict[str, Any]]:
    candidate_ids = tuple(candidate_ids)
    sharpe_kwargs = {
        "freq": pd.Timedelta(config.freq),
        "year_freq": pd.Timedelta(config.year_freq),
    }
    evidence_settings = portfolio_metric_assumptions(config) | {
        "scope_detail": "one shared cash group across symbols for each candidate",
    }
    stats, stats_warnings = _capture_warnings(
        lambda: pf.stats(metrics=list(PORTFOLIO_STATS_METRICS), agg_func=None)
    )
    per_symbol_stats, per_symbol_stats_warnings = _capture_warnings(
        lambda: pf.stats(
            metrics=list(PORTFOLIO_STATS_METRICS),
            agg_func=None,
            group_by=False,
        )
    )
    sharpe_ratio, sharpe_warnings = _capture_warnings(lambda: pf.get_sharpe_ratio(**sharpe_kwargs))
    per_symbol_sharpe, per_symbol_sharpe_warnings = _capture_warnings(
        lambda: pf.get_sharpe_ratio(
            **sharpe_kwargs,
            group_by=False,
        )
    )
    optional_diagnostics = _optional_diagnostics_by_candidate(
        pf,
        candidate_ids,
        sharpe_kwargs,
        evidence_settings,
    )

    metrics_by_candidate: dict[str, dict[str, Any]] = {}
    for candidate_id in candidate_ids:
        metrics: dict[str, Any] = {}
        metric_evidence: dict[str, Any] = {}
        per_symbol: dict[str, dict[str, Any]] = {}
        per_symbol_metric_evidence: dict[str, dict[str, Any]] = {}
        for metric_name, metric in PORTFOLIO_METRIC_CATALOG.items():
            vbt_metric = _vbt_metric_config(pf, metric["vbt_metric"])
            title = vbt_metric["title"]
            source = _metric_source(metric, title)
            if metric["source_method"] == "stats":
                raw_value = _candidate_stat_value(stats, title, candidate_id)
                raw_symbol_values = _candidate_symbol_stat_values(
                    per_symbol_stats,
                    title,
                    candidate_id,
                )
                warnings_for_metric = stats_warnings
                per_symbol_warnings = per_symbol_stats_warnings
            else:
                raw_value = _candidate_raw_value(sharpe_ratio, candidate_id)
                raw_symbol_values = _candidate_symbol_raw_values(per_symbol_sharpe, candidate_id)
                warnings_for_metric = sharpe_warnings
                per_symbol_warnings = per_symbol_sharpe_warnings

            evidence = _metric_evidence(
                metric_name,
                metric,
                source,
                raw_value,
                settings=evidence_settings,
                warning_records=warnings_for_metric,
            )
            symbol_evidence = {
                symbol: _metric_evidence(
                    metric_name,
                    metric,
                    source,
                    value,
                    settings=evidence_settings,
                    warning_records=per_symbol_warnings,
                )
                for symbol, value in raw_symbol_values.items()
            }
            metrics[metric_name] = evidence["value"]
            metric_evidence[metric_name] = evidence
            per_symbol[metric_name] = {
                symbol: evidence["value"] for symbol, evidence in symbol_evidence.items()
            }
            per_symbol_metric_evidence[metric_name] = symbol_evidence
        metrics_by_candidate[candidate_id] = {
            **metrics,
            "metric_scope": PORTFOLIO_METRIC_SCOPE,
            "metric_assumptions": evidence_settings,
            "metric_evidence": metric_evidence,
            "metric_roles": _metric_roles(),
            "optional_diagnostics": optional_diagnostics[candidate_id],
            "per_symbol": per_symbol,
            "per_symbol_metric_evidence": per_symbol_metric_evidence,
        }
    return metrics_by_candidate


def portfolio_metric_assumptions(config: ReportConfig) -> dict[str, Any]:
    return {
        "scope": PORTFOLIO_METRIC_SCOPE,
        "scope_detail": "one shared cash group across configured symbols",
        "freq": config.freq,
        "year_freq": config.year_freq,
        "benchmark_status": "none",
        "benchmark_source": None,
    }


def build_survival_report(
    experiment_name: str,
    train_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    config: ReportConfig,
    *,
    split_metric_evidence: Iterable[Mapping[str, Any]],
    validation_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation_metadata = validation_metadata or {}
    gate_outcomes = _validation_gate_outcomes(validation_metadata)
    test_rows = [row for row in split_metric_evidence if row.get("set") == "test"]
    if not test_rows:
        gate_outcomes.append(
            _gate_outcome(
                name="split_test_metric_evidence",
                metric=None,
                source_scope="per_split_test_metrics",
                status=GATE_STATUS_INSUFFICIENT_EVIDENCE,
                reason="Missing per-split test metric evidence for survival gates",
                actual_value=None,
                availability=METRIC_AVAILABILITY_UNAVAILABLE,
                threshold="present",
                comparator="is",
            )
        )
    else:
        gate_outcomes.extend(_split_threshold_gates(test_rows, config))
        gate_outcomes.append(_trade_gate(test_rows, config))

    status = _report_status(gate_outcomes)
    reasons = [gate["reason"] for gate in gate_outcomes if gate["status"] != GATE_STATUS_PASS]

    return {
        "experiment": experiment_name,
        "status": status,
        "validation": validation_metadata,
        "decision_policy": _decision_policy(config),
        "metric_roles": {
            "train_metrics": "descriptive_summary",
            "test_metrics": "descriptive_summary",
            "gate_evidence": "per_split_test_metrics",
        },
        "metric_evidence_summary": _metric_evidence_summary(test_rows),
        "gate_outcomes": gate_outcomes,
        "reasons": reasons or ["Per-split OOS metrics cleared configured survival gates"],
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
    }


def split_metric_evidence_row(split: str, set_name: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "split": split,
        "set": set_name,
        "metric_scope": metrics.get("metric_scope"),
        "metric_assumptions": metrics.get("metric_assumptions"),
        "metrics": {name: metrics.get(name) for name in METRIC_VALUE_KEYS},
        "metric_evidence": metrics.get("metric_evidence", {}),
        "optional_diagnostics": metrics.get("optional_diagnostics", {}),
        "per_symbol": metrics.get("per_symbol", {}),
        "per_symbol_metric_evidence": metrics.get("per_symbol_metric_evidence", {}),
    }


def write_report(report: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(to_builtin(report), indent=2, sort_keys=True) + "\n")


def _metric_roles() -> dict[str, Any]:
    return {
        metric_name: {
            "required_report_output": metric["required_report_output"],
            "required_gate_input": metric["required_gate_input"],
        }
        for metric_name, metric in PORTFOLIO_METRIC_CATALOG.items()
    }


def _decision_policy(config: ReportConfig) -> dict[str, Any]:
    return {
        "id": "split_first_survival_gates",
        "version": 1,
        "status_precedence": [
            GATE_STATUS_FAIL,
            GATE_STATUS_INVALID_VALIDATION,
            GATE_STATUS_UNAVAILABLE_METRIC,
            GATE_STATUS_INSUFFICIENT_EVIDENCE,
            GATE_STATUS_PASS,
        ],
        "metrics": {
            "sharpe_ratio": {
                "policy": "all_splits_pass",
                "threshold": config.min_oos_sharpe,
                "comparator": ">=",
                "rationale": "Every test split must meet the configured Sharpe floor.",
            },
            "max_drawdown_pct": {
                "policy": "all_splits_pass",
                "threshold": config.max_oos_drawdown * 100,
                "comparator": "<=",
                "unit": "percent_loss_magnitude",
                "rationale": "Every test split must stay within the configured drawdown cap.",
            },
            "total_trades": {
                "policy": "sum_across_test_splits",
                "threshold": config.min_oos_trades,
                "comparator": ">=",
                "rationale": "The current config names total out-of-sample trade sufficiency.",
            },
        },
    }


def _metric_evidence_summary(test_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not test_rows:
        return {
            "source_scope": "per_split_test_metrics",
            "metric_assumptions": None,
            "benchmark_status": None,
            "metrics": {},
            "optional_diagnostics": {},
        }

    metric_assumptions = test_rows[0].get("metric_assumptions")
    metrics: dict[str, Any] = {}
    optional_diagnostics: dict[str, Any] = {}
    for row in test_rows:
        split = str(row.get("split"))
        for metric_name, evidence in row.get("metric_evidence", {}).items():
            metric_summary = metrics.setdefault(
                metric_name,
                {
                    "required_report_output": evidence.get("required_report_output", False),
                    "required_gate_input": evidence.get("required_gate_input", False),
                    "unit": evidence.get("unit"),
                    "source": evidence.get("source"),
                    "settings": evidence.get("settings"),
                    "splits": [],
                },
            )
            metric_summary["splits"].append(
                {
                    "split": split,
                    "set": row.get("set"),
                    "value": evidence.get("value"),
                    "normalized_value": evidence.get("normalized_value"),
                    "availability": evidence.get("availability"),
                    "non_finite": evidence.get("non_finite"),
                    "warnings": evidence.get("warnings", []),
                }
            )
        if row.get("optional_diagnostics"):
            optional_diagnostics[split] = row["optional_diagnostics"]

    return {
        "source_scope": "per_split_test_metrics",
        "metric_assumptions": metric_assumptions,
        "benchmark_status": (
            metric_assumptions.get("benchmark_status")
            if isinstance(metric_assumptions, Mapping)
            else None
        ),
        "metrics": metrics,
        "optional_diagnostics": optional_diagnostics,
    }


def _validation_gate_outcomes(validation_metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    decision_grade = bool(validation_metadata.get("decision_grade", False))
    split_safety = validation_metadata.get("target", {}).get("split_safety", {})
    purging_missing = (
        decision_grade
        and split_safety.get("purging_required")
        and not split_purging_passed(validation_metadata.get("split_metadata"))
    )
    if purging_missing:
        decision_grade = False
        reason = "Validation is missing public split evidence for label-window purging"
    elif decision_grade:
        reason = "Validation evidence is decision-grade"
    else:
        reason = "Validation is non-decision-grade until purged CV is applied"
    return [
        _gate_outcome(
            name="validation_decision_grade",
            metric=None,
            source_scope="validation_metadata",
            status=GATE_STATUS_PASS if decision_grade else GATE_STATUS_INVALID_VALIDATION,
            reason=reason,
            actual_value=decision_grade,
            availability=METRIC_AVAILABILITY_AVAILABLE,
            threshold=True,
            comparator="is",
        )
    ]


def _split_threshold_gates(
    test_rows: list[Mapping[str, Any]],
    config: ReportConfig,
) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for row in test_rows:
        split = str(row.get("split"))
        sharpe = _row_metric_value(row, "sharpe_ratio")
        gates.append(
            _threshold_gate(
                name="oos_sharpe",
                metric="sharpe_ratio",
                split=split,
                metric_value=sharpe,
                threshold=config.min_oos_sharpe,
                comparator=">=",
                failed=lambda value: value < config.min_oos_sharpe,
                pass_reason=lambda value, split=split: (
                    f"OOS Sharpe passed on {split}: {value} >= {config.min_oos_sharpe}"
                ),
                fail_reason=lambda value, split=split: (
                    f"OOS Sharpe below threshold on {split}: {value} < {config.min_oos_sharpe}"
                ),
            )
        )
        drawdown = _row_metric_value(row, "max_drawdown_pct")
        threshold_pct = config.max_oos_drawdown * 100
        gates.append(
            _threshold_gate(
                name="oos_drawdown",
                metric="max_drawdown_pct",
                split=split,
                metric_value=drawdown,
                threshold=threshold_pct,
                comparator="<=",
                failed=lambda value, threshold_pct=threshold_pct: value > threshold_pct,
                pass_reason=lambda value, split=split, threshold_pct=threshold_pct: (
                    f"OOS drawdown passed on {split}: {value}% <= {threshold_pct}%"
                ),
                fail_reason=lambda value, split=split, threshold_pct=threshold_pct: (
                    f"OOS drawdown too high on {split}: {value}% > {threshold_pct}%"
                ),
            )
        )
    return gates


def _threshold_gate(
    *,
    name: str,
    metric: str,
    split: str,
    metric_value: dict[str, Any],
    threshold: float | int,
    comparator: str,
    failed: Callable[[float], bool],
    pass_reason: Callable[[float], str],
    fail_reason: Callable[[float], str],
) -> dict[str, Any]:
    value = metric_value["value"]
    availability = metric_value["availability"]
    if availability != METRIC_AVAILABILITY_AVAILABLE or value is None:
        return _gate_outcome(
            name=name,
            metric=metric,
            source_scope="per_split_test_metrics",
            split=split,
            status=GATE_STATUS_UNAVAILABLE_METRIC,
            reason=f"{metric} unavailable on {split}: {availability}",
            actual_value=value,
            availability=availability,
            threshold=threshold,
            comparator=comparator,
            evidence=metric_value.get("evidence"),
        )
    numeric_value = float(value)
    status = GATE_STATUS_FAIL if failed(numeric_value) else GATE_STATUS_PASS
    return _gate_outcome(
        name=name,
        metric=metric,
        source_scope="per_split_test_metrics",
        split=split,
        status=status,
        reason=fail_reason(numeric_value)
        if status == GATE_STATUS_FAIL
        else pass_reason(numeric_value),
        actual_value=numeric_value,
        availability=availability,
        threshold=threshold,
        comparator=comparator,
        evidence=metric_value.get("evidence"),
    )


def _trade_gate(test_rows: list[Mapping[str, Any]], config: ReportConfig) -> dict[str, Any]:
    trade_inputs = [_trade_gate_input(row) for row in test_rows]
    unavailable = [
        value for value in trade_inputs if value["availability"] != METRIC_AVAILABILITY_AVAILABLE
    ]
    if unavailable:
        return _gate_outcome(
            name="oos_trades",
            metric="total_trades",
            source_scope="per_split_test_metrics",
            status=GATE_STATUS_UNAVAILABLE_METRIC,
            reason="OOS trade count unavailable for one or more test splits",
            actual_value=None,
            availability=METRIC_AVAILABILITY_UNAVAILABLE,
            threshold=config.min_oos_trades,
            comparator=">=",
            inputs=trade_inputs,
        )
    total_trades = sum(float(value["value"]) for value in trade_inputs)
    status = (
        GATE_STATUS_PASS
        if total_trades >= config.min_oos_trades
        else GATE_STATUS_INSUFFICIENT_EVIDENCE
    )
    reason = (
        f"OOS trades passed: {total_trades:g} >= {config.min_oos_trades}"
        if status == GATE_STATUS_PASS
        else f"Too few OOS trades: {total_trades:g} < {config.min_oos_trades}"
    )
    return _gate_outcome(
        name="oos_trades",
        metric="total_trades",
        source_scope="per_split_test_metrics",
        status=status,
        reason=reason,
        actual_value=total_trades,
        availability=METRIC_AVAILABILITY_AVAILABLE,
        threshold=config.min_oos_trades,
        comparator=">=",
        inputs=trade_inputs,
    )


def _trade_gate_input(row: Mapping[str, Any]) -> dict[str, Any]:
    value = _row_metric_value(row, "total_trades")
    return {
        "split": row.get("split"),
        "set": row.get("set"),
        "metric": "total_trades",
        "value": value["value"],
        "availability": value["availability"],
        "evidence": value.get("evidence"),
    }


def _row_metric_value(row: Mapping[str, Any], metric: str) -> dict[str, Any]:
    metric_evidence = row.get("metric_evidence")
    if not isinstance(metric_evidence, Mapping):
        raise TypeError("split metric evidence row must include metric_evidence")
    evidence = metric_evidence.get(metric)
    if not isinstance(evidence, Mapping):
        raise TypeError(f"split metric evidence row must include {metric!r} evidence")

    availability = evidence.get("availability", METRIC_AVAILABILITY_UNAVAILABLE)
    value = evidence.get("normalized_value", evidence.get("value"))
    if availability != METRIC_AVAILABILITY_AVAILABLE:
        return {"value": None, "availability": availability, "evidence": evidence}
    return {
        "value": _gate_metric_value(metric, value),
        "availability": _scalar_availability(value),
        "evidence": evidence,
    }


def _gate_metric_value(metric: str, value: Any) -> Any:
    if _non_finite_reason(value) is not None:
        return None
    if metric == "max_drawdown_pct":
        return _drawdown_loss_magnitude_pct(value)
    return to_builtin(value)


def _scalar_availability(value: Any) -> str:
    return (
        METRIC_AVAILABILITY_UNAVAILABLE
        if _non_finite_reason(value) is not None
        else METRIC_AVAILABILITY_AVAILABLE
    )


def _report_status(gate_outcomes: list[dict[str, Any]]) -> str:
    required_gates = [gate for gate in gate_outcomes if gate.get("required", True)]
    validation_gate = next(
        (gate for gate in required_gates if gate["name"] == "validation_decision_grade"),
        None,
    )
    if validation_gate and validation_gate["status"] != GATE_STATUS_PASS:
        return REPORT_STATUS_NEEDS_MORE_EVIDENCE
    if any(gate["status"] == GATE_STATUS_FAIL for gate in required_gates):
        return REPORT_STATUS_REJECTED
    if any(gate["status"] != GATE_STATUS_PASS for gate in required_gates):
        return REPORT_STATUS_NEEDS_MORE_EVIDENCE
    return REPORT_STATUS_SURVIVED


def _gate_outcome(
    *,
    name: str,
    metric: str | None,
    source_scope: str,
    status: str,
    reason: str,
    actual_value: Any,
    availability: str,
    threshold: Any,
    comparator: str,
    split: str | None = None,
    evidence: Any = None,
    inputs: list[dict[str, Any]] | None = None,
    required: bool = True,
) -> dict[str, Any]:
    outcome = {
        "name": name,
        "metric": metric,
        "source_scope": source_scope,
        "split": split,
        "actual_value": to_builtin(actual_value),
        "availability": availability,
        "threshold": to_builtin(threshold),
        "comparator": comparator,
        "status": status,
        "reason": reason,
        "required": required,
    }
    if evidence is not None:
        outcome["evidence"] = to_builtin(evidence)
    if inputs is not None:
        outcome["inputs"] = to_builtin(inputs)
    return outcome


def _capture_warnings(call: Callable[[], Any]) -> tuple[Any, list[dict[str, str]]]:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        value = call()
    return value, [_warning_record(warning) for warning in captured]


def _warning_record(warning: warnings.WarningMessage) -> dict[str, str]:
    return {
        "category": warning.category.__name__,
        "message": str(warning.message),
    }


def _vbt_metric_config(pf: Any, metric_identity: str) -> dict[str, Any]:
    try:
        metric = pf.metrics[metric_identity]
    except KeyError as error:
        raise ValueError(
            f"VectorBT metric identity {metric_identity!r} is not registered"
        ) from error
    title = metric.get("title")
    if not title:
        raise ValueError(f"VectorBT metric identity {metric_identity!r} has no title")
    return dict(metric)


def _metric_source(metric: Mapping[str, Any], title: str) -> dict[str, Any]:
    return {
        "engine": "vectorbtpro",
        "identity": metric["vbt_metric"],
        "title": title,
        "method": metric["source_method"],
    }


def _metric_evidence(
    metric_name: str,
    metric: Mapping[str, Any],
    source: Mapping[str, Any],
    raw_value: Any,
    *,
    settings: Mapping[str, Any],
    warning_records: list[dict[str, str]],
) -> dict[str, Any]:
    non_finite = _non_finite_reason(raw_value)
    if non_finite is None and metric.get("required_gate_input"):
        non_finite = _warning_unavailability_reason(metric_name, warning_records)
    value = None if non_finite else _normalized_metric_value(metric_name, raw_value)
    availability = METRIC_AVAILABILITY_UNAVAILABLE if non_finite else METRIC_AVAILABILITY_AVAILABLE
    return {
        "name": metric_name,
        "value": value,
        "raw_value": None if non_finite else to_builtin(raw_value),
        "normalized_value": value,
        "availability": availability,
        "non_finite": non_finite,
        "unit": metric["unit"],
        "source": dict(source),
        "settings": dict(settings),
        "warnings": warning_records,
        "required_report_output": bool(metric["required_report_output"]),
        "required_gate_input": bool(metric["required_gate_input"]),
    }


def _warning_unavailability_reason(
    metric_name: str,
    warning_records: list[dict[str, str]],
) -> str | None:
    if metric_name not in {"sharpe_ratio"}:
        return None
    for warning_record in warning_records:
        message = warning_record["message"].lower()
        if any(term in message for term in ("freq", "frequency", "annual", "skipped", "requires")):
            return "metric_warning"
    return None


def _optional_diagnostics(
    pf: Any,
    sharpe_kwargs: dict[str, Any],
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    for name, spec in OPTIONAL_DIAGNOSTICS.items():
        method_name = spec["method"]
        if not hasattr(pf, method_name):
            diagnostics[name] = _unavailable_diagnostic(
                name, spec, settings, "method not available"
            )
            continue
        try:
            raw_value, warning_records = _capture_warnings(
                lambda method_name=method_name: getattr(pf, method_name)(**sharpe_kwargs)
            )
            diagnostics[name] = _metric_evidence(
                name,
                {
                    "unit": spec["unit"],
                    "required_report_output": False,
                    "required_gate_input": False,
                },
                {
                    "engine": "vectorbtpro",
                    "identity": spec["vbt_metric"],
                    "title": name,
                    "method": method_name,
                },
                _headline_raw_value(raw_value),
                settings=settings,
                warning_records=warning_records,
            )
        except Exception as error:
            diagnostics[name] = _unavailable_diagnostic(name, spec, settings, str(error))
    return diagnostics


def _optional_diagnostics_by_candidate(
    pf: Any,
    candidate_ids: Iterable[str],
    sharpe_kwargs: dict[str, Any],
    settings: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    diagnostics = {candidate_id: {} for candidate_id in candidate_ids}
    for name, spec in OPTIONAL_DIAGNOSTICS.items():
        method_name = spec["method"]
        if not hasattr(pf, method_name):
            for candidate_id in diagnostics:
                diagnostics[candidate_id][name] = _unavailable_diagnostic(
                    name, spec, settings, "method not available"
                )
            continue
        try:
            raw_value, warning_records = _capture_warnings(
                lambda method_name=method_name: getattr(pf, method_name)(**sharpe_kwargs)
            )
        except Exception as error:
            for candidate_id in diagnostics:
                diagnostics[candidate_id][name] = _unavailable_diagnostic(
                    name, spec, settings, str(error)
                )
            continue
        for candidate_id in diagnostics:
            diagnostics[candidate_id][name] = _metric_evidence(
                name,
                {
                    "unit": spec["unit"],
                    "required_report_output": False,
                    "required_gate_input": False,
                },
                {
                    "engine": "vectorbtpro",
                    "identity": spec["vbt_metric"],
                    "title": name,
                    "method": method_name,
                },
                _candidate_raw_value(raw_value, candidate_id),
                settings=settings,
                warning_records=warning_records,
            )
    return diagnostics


def _unavailable_diagnostic(
    name: str,
    spec: Mapping[str, Any],
    settings: Mapping[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": None,
        "raw_value": None,
        "normalized_value": None,
        "availability": METRIC_AVAILABILITY_NOT_CONFIGURED,
        "non_finite": "unavailable",
        "unit": spec["unit"],
        "source": {
            "engine": "vectorbtpro",
            "identity": spec["vbt_metric"],
            "title": name,
            "method": spec["method"],
        },
        "settings": dict(settings),
        "warnings": [],
        "reason": reason,
        "required_report_output": False,
        "required_gate_input": False,
    }


def _raw_metric_map(stats: Any, name: str) -> dict[str, Any]:
    if isinstance(stats, pd.DataFrame):
        if name in stats.index:
            return _raw_value_map(stats.loc[name])
        if name in stats.columns:
            return _raw_value_map(stats[name])
        return {}
    return {"portfolio": stats.get(name)}


def _candidate_stat_value(stats: Any, title: str, candidate_id: str) -> Any:
    if isinstance(stats, pd.DataFrame):
        if candidate_id in stats.index and title in stats.columns:
            return stats.loc[candidate_id, title]
        if title in stats.index and candidate_id in stats.columns:
            return stats.loc[title, candidate_id]
    if isinstance(stats, pd.Series):
        return stats.get(candidate_id)
    return None


def _candidate_symbol_stat_values(stats: Any, title: str, candidate_id: str) -> dict[str, Any]:
    if not isinstance(stats, pd.DataFrame):
        return {}
    if title not in stats.columns:
        return {}
    values = stats[title]
    if not isinstance(values.index, pd.MultiIndex) or "candidate_id" not in values.index.names:
        return {}
    if candidate_id not in values.index.get_level_values("candidate_id"):
        return {}
    candidate_values = values.xs(candidate_id, level="candidate_id")
    return {str(symbol): value for symbol, value in candidate_values.items()}


def _candidate_raw_value(value: Any, candidate_id: str) -> Any:
    if isinstance(value, pd.DataFrame):
        if candidate_id in value.index and len(value.columns) == 1:
            return value.iloc[value.index.get_loc(candidate_id), 0]
        if candidate_id in value.columns and len(value.index) == 1:
            return value.loc[value.index[0], candidate_id]
    if isinstance(value, pd.Series):
        return value.get(candidate_id)
    return value


def _candidate_symbol_raw_values(value: Any, candidate_id: str) -> dict[str, Any]:
    if not isinstance(value, pd.Series):
        return {}
    if not isinstance(value.index, pd.MultiIndex) or "candidate_id" not in value.index.names:
        return {}
    if candidate_id not in value.index.get_level_values("candidate_id"):
        return {}
    candidate_values = value.xs(candidate_id, level="candidate_id")
    return {str(symbol): item for symbol, item in candidate_values.items()}


def _headline_raw_metric(stats: Any, name: str) -> Any:
    values = _raw_metric_map(stats, name)
    if not values:
        return None
    return _headline_from_values(values)


def _headline_raw_value(value: Any) -> Any:
    return _headline_from_values(_raw_value_map(value))


def _headline_from_values(values: dict[str, Any]) -> Any:
    if len(values) != 1:
        raise ValueError("shared-cash headline metrics must resolve to exactly one group")
    return next(iter(values.values()))


def _raw_value_map(value: Any) -> dict[str, Any]:
    if isinstance(value, pd.DataFrame):
        return {
            "__".join(map(str, key)) if isinstance(key, tuple) else str(key): item
            for key, item in value.stack().items()
        }
    if isinstance(value, pd.Series):
        return {str(key): item for key, item in value.items()}
    return {"portfolio": value}


def _normalized_metric_value(metric_name: str, value: Any) -> Any:
    if metric_name == "max_drawdown_pct":
        return _drawdown_loss_magnitude_pct(value)
    return to_builtin(value)


def _drawdown_loss_magnitude_pct(value: Any) -> float:
    return abs(float(value))


def _non_finite_reason(value: Any) -> str | None:
    if isinstance(value, (pd.Series, pd.DataFrame)):
        raise TypeError("metric value must be scalar")
    if value is None:
        return "missing"
    try:
        if pd.isna(value):
            return "nan"
    except (TypeError, ValueError):
        pass
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return "nan"
    if math.isinf(numeric):
        return "positive_infinity" if numeric > 0 else "negative_infinity"
    return None
