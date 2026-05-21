from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.optimization.evidence import _canonical_value
from research.aegis_research.optimization.runner import METRIC_INDEX_NAME

OPTIMIZATION_LEADERBOARD_SCHEMA_VERSION = "optimization_leaderboard.v1"
WEIGHT_BASIS = "held_out_row_count"


def build_optimization_leaderboard(
    *,
    selection: pd.Series,
    candidate_rows: Sequence[Mapping[str, Any]],
    split_held_out_row_counts: Mapping[Any, int],
    ranking_metric: str,
    ranking_direction: str,
    metric_registry_fingerprint: str | None = None,
) -> dict[str, Any]:
    candidate_by_params = {
        _canonical_params_key(candidate["params"]): candidate for candidate in candidate_rows
    }
    held_out = selection.xs("held_out", level="set")
    if not isinstance(held_out.index, pd.MultiIndex):
        raise TypeError("selection index must be a MultiIndex with split, params, and metric levels")
    level_names = list(held_out.index.names)
    if "split" not in level_names or METRIC_INDEX_NAME not in level_names:
        raise ValueError(
            f"selection index must include 'split' and {METRIC_INDEX_NAME!r} levels; got {level_names}"
        )
    param_levels = [name for name in level_names if name not in {"split", METRIC_INDEX_NAME}]
    pivoted = held_out.unstack(level=METRIC_INDEX_NAME)
    metric_columns = [name for name in pivoted.columns if name in PORTFOLIO_METRIC_VALUE_KEYS]
    pivoted = pivoted[metric_columns]

    aggregate: dict[str, dict[str, Any]] = {}
    attempted_splits: set[Any] = set()
    failure_samples: list[dict[str, str]] = []
    eligible_split_count = len(split_held_out_row_counts)
    for index_key, row in pivoted.iterrows():
        if not isinstance(index_key, tuple):
            index_key = (index_key,)
        params_dict = dict(zip(param_levels, index_key[1:], strict=True))
        split_label = index_key[0]
        attempted_splits.add(split_label)
        canonical_key = _canonical_params_key(
            {name: _canonical_value(value) for name, value in params_dict.items()}
        )
        candidate = candidate_by_params.get(canonical_key)
        if candidate is None:
            _append_failure(
                failure_samples,
                str(split_label),
                f"split {split_label} winner params {params_dict!r} not present in candidate evidence",
            )
            continue
        weight = float(split_held_out_row_counts.get(split_label, 0))
        if weight <= 0:
            _append_failure(
                failure_samples,
                str(split_label),
                f"split {split_label} has zero held-out row count; cannot weight aggregate",
            )
            continue
        bucket = aggregate.setdefault(
            candidate["candidate_key"],
            {
                "candidate_key": candidate["candidate_key"],
                "params": dict(candidate["params"]),
                "metric_sums": dict.fromkeys(PORTFOLIO_METRIC_VALUE_KEYS, 0.0),
                "metric_weights": dict.fromkeys(PORTFOLIO_METRIC_VALUE_KEYS, 0.0),
                "split_refs": set(),
                "oos_ranking_values": [],
            },
        )
        bucket["split_refs"].add(split_label)
        ranking_value: float | None = None
        for metric_name in metric_columns:
            value = row[metric_name]
            if isinstance(value, float) and math.isnan(value):
                continue
            bucket["metric_sums"][metric_name] += float(value) * weight
            bucket["metric_weights"][metric_name] += weight
            if metric_name == ranking_metric:
                ranking_value = float(value)
        if ranking_value is None:
            _append_failure(
                failure_samples,
                bucket["candidate_key"],
                f"split {split_label} ranking metric {ranking_metric!r} unavailable for winner",
            )
        else:
            bucket["oos_ranking_values"].append(ranking_value)

    rows: list[dict[str, Any]] = []
    for bucket in aggregate.values():
        metrics_aggregate: dict[str, float | None] = {}
        for metric_name in PORTFOLIO_METRIC_VALUE_KEYS:
            weight_total = bucket["metric_weights"][metric_name]
            if weight_total > 0:
                metrics_aggregate[metric_name] = (
                    bucket["metric_sums"][metric_name] / weight_total
                )
            else:
                metrics_aggregate[metric_name] = None
        oos_values = bucket["oos_ranking_values"]
        split_refs = sorted(bucket["split_refs"])
        held_out_row_count = sum(
            int(split_held_out_row_counts.get(split, 0)) for split in split_refs
        )
        rows.append(
            {
                "candidate_key": bucket["candidate_key"],
                "params": bucket["params"],
                "ranking_metric": ranking_metric,
                "ranking_direction": ranking_direction,
                "ranking_metric_value": metrics_aggregate[ranking_metric],
                "metrics": metrics_aggregate,
                "selected_split_count": len(split_refs),
                "eligible_split_count": eligible_split_count,
                "split_refs": split_refs,
                "weight_basis": WEIGHT_BASIS,
                "held_out_row_count": held_out_row_count,
                "oos_metric_values": oos_values,
                "oos_metric_min": min(oos_values) if oos_values else None,
                "oos_metric_max": max(oos_values) if oos_values else None,
            }
        )
    def _sort_key(row: dict[str, Any]) -> tuple[int, float]:
        value = row["ranking_metric_value"]
        if value is None:
            # Push missing values to the end regardless of direction.
            return (1, 0.0)
        if ranking_direction == "desc":
            return (0, -float(value))
        return (0, float(value))

    rows.sort(key=_sort_key)
    return {
        "schema_version": OPTIMIZATION_LEADERBOARD_SCHEMA_VERSION,
        "ranking_metric": ranking_metric,
        "ranking_direction": ranking_direction,
        "metric_registry_fingerprint": metric_registry_fingerprint,
        "weight_basis": WEIGHT_BASIS,
        "summary": {
            "attempted_splits": len(attempted_splits),
            "selected_splits": sum(row["selected_split_count"] for row in rows),
            "unique_winner_count": len(rows),
        },
        "rows": rows,
        "failure_samples": failure_samples[:10],
    }


def _canonical_params_key(params: Mapping[str, Any]) -> str:
    canonical = {str(key): _canonical_value(value) for key in sorted(params) for value in [params[key]]}
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _append_failure(failures: list[dict[str, str]], subject: str, message: str) -> None:
    failures.append({"subject": subject, "message": message})
