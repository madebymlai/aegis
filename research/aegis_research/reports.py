from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import pandas as pd

from research.aegis_research.config import ReportConfig, to_builtin
from research.aegis_research.metrics.stats import (
    PORTFOLIO_METRIC_CATALOG,
    PORTFOLIO_METRIC_VALUE_KEYS,
    PORTFOLIO_STATS_METRICS,
)

PORTFOLIO_METRIC_SCOPE = "shared_cash_group"
METRICS_SCHEMA_VERSION = "metrics.v3"
METRIC_AVAILABILITY_AVAILABLE = "available"
METRIC_AVAILABILITY_UNAVAILABLE = "unavailable_metric"
METRIC_AVAILABILITY_NOT_CONFIGURED = "not_configured"
METRIC_VALUE_KEYS = PORTFOLIO_METRIC_VALUE_KEYS
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


def _metric_roles() -> dict[str, Any]:
    return {
        metric_name: {
            "required_report_output": metric["required_report_output"],
            "required_gate_input": metric["required_gate_input"],
        }
        for metric_name, metric in PORTFOLIO_METRIC_CATALOG.items()
    }


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
        if title in stats.index:
            return stats.get(title)
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
    if metric_name == "max_dd":
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
