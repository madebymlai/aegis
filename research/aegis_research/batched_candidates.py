from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import product
from typing import Any, Literal

import pandas as pd

from research.aegis_research.component_registry.manifests import COMPONENT_ID_RE

BATCHED_PLAYBOOK_CONTRACT = "aegis.batched_playbook.v1"
CANDIDATE_LEVEL = "candidate_id"
SYMBOL_LEVEL = "symbol"

INDICATOR_RESULT_KIND = "indicator_surface"
STRATEGY_AXIS_KIND = "strategy_axis"
STRATEGY_SIGNALS_KIND = "strategy_signals"
STRATEGY_MATERIALIZER_KEY = "materialize_signals"

BatchedSourceKind = Literal["component", "playbook"]

PLAYBOOK_METRIC_SOURCE_KEYS = frozenset(
    {
        "baseline_metric_source",
        "baseline_metrics",
        "metric_source",
        "metrics",
    }
)
PORTFOLIO_FIELD_KEYS = frozenset(
    {
        "costs",
        "direction",
        "entry_budget",
        "execution_timing",
        "fees",
        "portfolio",
        "portfolio_config",
        "price",
        "size",
        "sizing",
        "slippage",
    }
)
SIGNAL_FIELD_KEYS = frozenset({"entries", "exits"})


class BatchedContractError(ValueError):
    pass


@dataclass(frozen=True)
class BatchedCandidate:
    candidate_id: str
    params: dict[str, Any]


@dataclass(frozen=True)
class BatchedCandidateAxis:
    source: BatchedSourceKind
    source_id: str
    candidates: tuple[BatchedCandidate, ...]

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(candidate.candidate_id for candidate in self.candidates)

    @property
    def count(self) -> int:
        return len(self.candidates)


@dataclass(frozen=True)
class BatchedCandidateRef:
    source: BatchedSourceKind
    source_id: str
    candidate_id: str
    params: dict[str, Any]


@dataclass(frozen=True)
class BatchedComposedCandidate:
    candidate_id: str
    strategy: BatchedCandidateRef
    indicators: tuple[BatchedCandidateRef, ...]


@dataclass(frozen=True)
class BatchedIndicatorResult:
    axis: BatchedCandidateAxis
    outputs: dict[str, pd.DataFrame]
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class BatchedStrategySignalResult:
    entries: pd.DataFrame
    exits: pd.DataFrame
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class BatchedSignalRequest:
    candidates: tuple[BatchedComposedCandidate, ...]

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(candidate.candidate_id for candidate in self.candidates)


@dataclass(frozen=True)
class BatchedStrategyPlan:
    axis: BatchedCandidateAxis
    materialize_signals: Callable[[BatchedSignalRequest], Mapping[str, Any]]
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class IndicatorAxisPreflight:
    source: BatchedSourceKind
    source_id: str
    candidate_count: int
    output_count: int
    row_count: int
    symbol_count: int
    estimated_cells: int


@dataclass(frozen=True)
class IndicatorGridPreflight:
    axes: tuple[IndicatorAxisPreflight, ...]
    indicator_context_count: int
    estimated_cells: int
    max_candidates: int
    max_estimated_cells: int

    def diagnostics(self) -> dict[str, Any]:
        return {
            "schema_version": "batched_indicator_preflight.v1",
            "indicator_axis_count": len(self.axes),
            "indicator_context_count": self.indicator_context_count,
            "estimated_cells": self.estimated_cells,
            "limits": {
                "max_candidates": self.max_candidates,
                "max_estimated_cells": self.max_estimated_cells,
            },
            "axes": [
                {
                    "source": axis.source,
                    "id": axis.source_id,
                    "candidate_count": axis.candidate_count,
                    "output_count": axis.output_count,
                    "row_count": axis.row_count,
                    "symbol_count": axis.symbol_count,
                    "estimated_cells": axis.estimated_cells,
                }
                for axis in self.axes
            ],
        }


def is_batched_playbook_result(result: Any) -> bool:
    return isinstance(result, Mapping) and result.get("contract") == BATCHED_PLAYBOOK_CONTRACT


def reject_batched_result_in_record_runner(result: Any, *, source_id: str) -> None:
    if is_batched_playbook_result(result):
        raise BatchedContractError(
            f"playbook {source_id!r} emitted batched contract {BATCHED_PLAYBOOK_CONTRACT!r}; "
            "run with the batched playbook path instead of legacy variant_records"
        )


def validate_batched_indicator_result(
    result: Any,
    *,
    source_id: str,
    close: pd.DataFrame,
) -> BatchedIndicatorResult:
    result = _validated_header(
        result,
        source_id=source_id,
        expected_kind=INDICATOR_RESULT_KIND,
        allowed_keys={"contract", "kind", "candidate_axis", "outputs", "diagnostics"},
    )
    axis = _candidate_axis(result, source="playbook", source_id=source_id)
    outputs = result.get("outputs")
    if not isinstance(outputs, Mapping) or not outputs:
        raise TypeError(f"playbook {source_id!r} batched indicator outputs must be a mapping")

    validated_outputs: dict[str, pd.DataFrame] = {}
    for name, value in outputs.items():
        if not isinstance(name, str) or not name:
            raise TypeError(f"playbook {source_id!r} batched indicator output names must be strings")
        validated_outputs[name] = _candidate_surface_frame(
            value,
            close=close,
            source_id=source_id,
            field_name=f"outputs.{name}",
            expected_candidate_ids=axis.candidate_ids,
        )
    return BatchedIndicatorResult(
        axis=axis,
        outputs=validated_outputs,
        diagnostics=_diagnostics(result),
    )


def validate_batched_strategy_axis(
    result: Any,
    *,
    source_id: str,
) -> BatchedCandidateAxis:
    result = _validated_header(
        result,
        source_id=source_id,
        expected_kind=STRATEGY_AXIS_KIND,
        allowed_keys={"contract", "kind", "candidate_axis", "diagnostics"},
    )
    return _candidate_axis(result, source="playbook", source_id=source_id)


def validate_batched_strategy_plan(
    result: Any,
    *,
    source_id: str,
) -> BatchedStrategyPlan:
    result = _validated_header(
        result,
        source_id=source_id,
        expected_kind=STRATEGY_AXIS_KIND,
        allowed_keys={
            "contract",
            "kind",
            "candidate_axis",
            STRATEGY_MATERIALIZER_KEY,
            "diagnostics",
        },
    )
    materialize = result.get(STRATEGY_MATERIALIZER_KEY)
    if not callable(materialize):
        raise TypeError(
            f"playbook {source_id!r} batched strategy axis must include callable "
            f"{STRATEGY_MATERIALIZER_KEY!r}"
        )
    return BatchedStrategyPlan(
        axis=_candidate_axis(result, source="playbook", source_id=source_id),
        materialize_signals=materialize,
        diagnostics=_diagnostics(result),
    )


def materialize_batched_strategy_signals(
    plan: BatchedStrategyPlan,
    *,
    source_id: str,
    requested_candidate_ids: Sequence[str],
    indicator_axes: Sequence[BatchedCandidateAxis] = (),
    close: pd.DataFrame,
) -> BatchedStrategySignalResult:
    candidate_grid = compose_batched_candidate_grid(
        strategy_axis=plan.axis,
        indicator_axes=indicator_axes,
    )
    requested = _requested_composed_candidates(
        requested_candidate_ids,
        candidates=candidate_grid,
        source_id=source_id,
    )
    return validate_batched_strategy_signals(
        plan.materialize_signals(BatchedSignalRequest(candidates=requested)),
        source_id=source_id,
        expected_candidate_ids=tuple(candidate.candidate_id for candidate in requested),
        close=close,
    )


def validate_batched_strategy_signals(
    result: Any,
    *,
    source_id: str,
    expected_candidate_ids: Sequence[str],
    close: pd.DataFrame,
) -> BatchedStrategySignalResult:
    result = _validated_header(
        result,
        source_id=source_id,
        expected_kind=STRATEGY_SIGNALS_KIND,
        allowed_keys={"contract", "kind", "entries", "exits", "diagnostics"},
    )
    expected = _expected_candidate_ids(expected_candidate_ids, source_id=source_id)
    if "entries" not in result or "exits" not in result:
        raise ValueError(f"playbook {source_id!r} batched strategy signals must include entries and exits")
    entries = _candidate_surface_frame(
        result["entries"],
        close=close,
        source_id=source_id,
        field_name="entries",
        expected_candidate_ids=expected,
    ).fillna(False).astype(bool)
    exits = _candidate_surface_frame(
        result["exits"],
        close=close,
        source_id=source_id,
        field_name="exits",
        expected_candidate_ids=expected,
    ).fillna(False).astype(bool)
    return BatchedStrategySignalResult(
        entries=entries,
        exits=exits,
        diagnostics=_diagnostics(result),
    )


def composed_candidate_ids(
    *,
    strategy_axis: BatchedCandidateAxis,
    indicator_axes: Sequence[BatchedCandidateAxis] = (),
) -> tuple[str, ...]:
    return tuple(
        candidate.candidate_id
        for candidate in compose_batched_candidate_grid(
            strategy_axis=strategy_axis,
            indicator_axes=indicator_axes,
        )
    )


def compose_batched_candidate_grid(
    *,
    strategy_axis: BatchedCandidateAxis,
    indicator_axes: Sequence[BatchedCandidateAxis] = (),
) -> tuple[BatchedComposedCandidate, ...]:
    indicator_products = tuple(product(*(axis.candidates for axis in indicator_axes))) or ((),)
    candidates: list[BatchedComposedCandidate] = []
    for indicators in indicator_products:
        indicator_refs = tuple(
            BatchedCandidateRef(
                source=axis.source,
                source_id=axis.source_id,
                candidate_id=candidate.candidate_id,
                params=dict(candidate.params),
            )
            for axis, candidate in zip(indicator_axes, indicators, strict=True)
        )
        indicator_tokens = [
            f"{ref.source}:{ref.source_id}:{ref.candidate_id}" for ref in indicator_refs
        ]
        for strategy_candidate in strategy_axis.candidates:
            strategy_ref = BatchedCandidateRef(
                source=strategy_axis.source,
                source_id=strategy_axis.source_id,
                candidate_id=strategy_candidate.candidate_id,
                params=dict(strategy_candidate.params),
            )
            if indicator_tokens:
                candidate_id = (
                    f"strategy:{strategy_axis.source}:{strategy_axis.source_id}:"
                    f"{strategy_candidate.candidate_id}+indicators:[{','.join(indicator_tokens)}]"
                )
            else:
                candidate_id = strategy_candidate.candidate_id
            candidates.append(
                BatchedComposedCandidate(
                    candidate_id=candidate_id,
                    strategy=strategy_ref,
                    indicators=indicator_refs,
                )
            )
    seen_ids: set[str] = set()
    duplicates: set[str] = set()
    for candidate in candidates:
        if candidate.candidate_id in seen_ids:
            duplicates.add(candidate.candidate_id)
        seen_ids.add(candidate.candidate_id)
    if duplicates:
        raise BatchedContractError(f"duplicate composed candidate ids: {sorted(duplicates)}")
    return tuple(candidates)


def preflight_indicator_grid(
    indicator_results: Sequence[BatchedIndicatorResult],
    *,
    max_candidates: int,
    max_estimated_cells: int,
) -> IndicatorGridPreflight:
    axes = tuple(_indicator_axis_preflight(result) for result in indicator_results)
    indicator_context_count = 1
    for axis in axes:
        indicator_context_count *= axis.candidate_count
    estimated_cells = sum(axis.estimated_cells for axis in axes)
    if indicator_context_count > max_candidates:
        raise BatchedContractError(
            f"batched indicator grid has {indicator_context_count} candidates, above "
            f"candidate_grid.max_candidates={max_candidates}"
        )
    if estimated_cells > max_estimated_cells:
        raise BatchedContractError(
            f"batched indicator grid has {estimated_cells} estimated cells, above "
            f"candidate_grid.max_estimated_cells={max_estimated_cells}"
        )
    return IndicatorGridPreflight(
        axes=axes,
        indicator_context_count=indicator_context_count,
        estimated_cells=estimated_cells,
        max_candidates=max_candidates,
        max_estimated_cells=max_estimated_cells,
    )


def _validated_header(
    result: Any,
    *,
    source_id: str,
    expected_kind: str,
    allowed_keys: set[str],
) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        raise TypeError(f"playbook {source_id!r} batched result must be a mapping")
    if "variant_records" in result:
        raise BatchedContractError(
            f"playbook {source_id!r} emitted legacy variant_records; "
            f"batched playbooks must use contract {BATCHED_PLAYBOOK_CONTRACT!r}"
        )
    if result.get("contract") != BATCHED_PLAYBOOK_CONTRACT:
        raise BatchedContractError(
            f"playbook {source_id!r} batched result contract must be "
            f"{BATCHED_PLAYBOOK_CONTRACT!r}"
        )
    if result.get("kind") != expected_kind:
        raise BatchedContractError(
            f"playbook {source_id!r} batched result kind must be {expected_kind!r}"
        )
    forbidden = sorted(set(result) & (PLAYBOOK_METRIC_SOURCE_KEYS | PORTFOLIO_FIELD_KEYS))
    if forbidden:
        raise BatchedContractError(
            f"playbook {source_id!r} batched result must not contain metric or portfolio fields: "
            f"{forbidden}"
        )
    unsupported = sorted(set(result) - allowed_keys)
    if unsupported:
        raise BatchedContractError(
            f"playbook {source_id!r} batched result contains unsupported fields: {unsupported}"
        )
    return result


def _indicator_axis_preflight(result: BatchedIndicatorResult) -> IndicatorAxisPreflight:
    first_output = next(iter(result.outputs.values()))
    symbol_count = len(first_output.columns.get_level_values(SYMBOL_LEVEL).unique())
    row_count = len(first_output.index)
    output_count = len(result.outputs)
    estimated_cells = result.axis.count * output_count * row_count * symbol_count
    return IndicatorAxisPreflight(
        source=result.axis.source,
        source_id=result.axis.source_id,
        candidate_count=result.axis.count,
        output_count=output_count,
        row_count=row_count,
        symbol_count=symbol_count,
        estimated_cells=estimated_cells,
    )


def _candidate_axis(
    result: Mapping[str, Any],
    *,
    source: BatchedSourceKind,
    source_id: str,
) -> BatchedCandidateAxis:
    raw_candidates = result.get("candidate_axis")
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes)):
        raise TypeError(f"playbook {source_id!r} candidate_axis must be a list")
    if not raw_candidates:
        raise BatchedContractError(f"playbook {source_id!r} candidate_axis must not be empty")

    candidates: list[BatchedCandidate] = []
    seen_ids: set[str] = set()
    for index, raw_candidate in enumerate(raw_candidates):
        if not isinstance(raw_candidate, Mapping):
            raise TypeError(f"playbook {source_id!r} candidate_axis[{index}] must be a mapping")
        unsupported = sorted(set(raw_candidate) - {"candidate_id", "params"})
        if unsupported:
            raise BatchedContractError(
                f"playbook {source_id!r} candidate_axis[{index}] contains unsupported fields: "
                f"{unsupported}"
            )
        candidate_id = raw_candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise TypeError(
                f"playbook {source_id!r} candidate_axis[{index}].candidate_id must be "
                "a non-empty string"
            )
        _validate_candidate_id(candidate_id, source_id=source_id, index=index)
        if candidate_id in seen_ids:
            raise BatchedContractError(
                f"playbook {source_id!r} emitted duplicate candidate {candidate_id!r}"
            )
        seen_ids.add(candidate_id)
        params = raw_candidate.get("params")
        if not isinstance(params, Mapping):
            raise TypeError(
                f"playbook {source_id!r} candidate_axis[{index}].params must be a mapping"
            )
        candidates.append(BatchedCandidate(candidate_id=candidate_id, params=dict(params)))
    return BatchedCandidateAxis(source=source, source_id=source_id, candidates=tuple(candidates))


def _candidate_surface_frame(
    value: Any,
    *,
    close: pd.DataFrame,
    source_id: str,
    field_name: str,
    expected_candidate_ids: tuple[str, ...],
) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        raise TypeError(f"playbook {source_id!r} batched {field_name} must be a pandas DataFrame")
    if not value.index.equals(close.index):
        raise BatchedContractError(f"playbook {source_id!r} batched {field_name} has misaligned timestamps")
    if not isinstance(value.columns, pd.MultiIndex):
        raise TypeError(
            f"playbook {source_id!r} batched {field_name} columns must be a MultiIndex "
            f"with {CANDIDATE_LEVEL!r} and {SYMBOL_LEVEL!r} levels"
        )
    if value.columns.has_duplicates:
        raise BatchedContractError(f"playbook {source_id!r} batched {field_name} columns duplicate candidate-symbol pairs")
    column_names = list(value.columns.names)
    if column_names.count(CANDIDATE_LEVEL) != 1 or column_names.count(SYMBOL_LEVEL) != 1:
        raise BatchedContractError(
            f"playbook {source_id!r} batched {field_name} columns must include exactly one "
            f"{CANDIDATE_LEVEL!r} level and one {SYMBOL_LEVEL!r} level"
        )

    candidate_values = value.columns.get_level_values(CANDIDATE_LEVEL)
    actual_candidate_ids = tuple(dict.fromkeys(str(candidate_id) for candidate_id in candidate_values))
    if actual_candidate_ids != expected_candidate_ids:
        raise BatchedContractError(
            f"playbook {source_id!r} batched {field_name} candidate axis mismatch: "
            f"expected {list(expected_candidate_ids)!r}, got {list(actual_candidate_ids)!r}"
        )

    expected_symbols = [str(column) for column in close.columns]
    symbol_values = value.columns.get_level_values(SYMBOL_LEVEL)
    expected_column_count = len(expected_candidate_ids) * len(expected_symbols)
    if len(value.columns) != expected_column_count:
        raise BatchedContractError(
            f"playbook {source_id!r} batched {field_name} must have one column per "
            "candidate-symbol pair"
        )
    for candidate_id in expected_candidate_ids:
        mask = candidate_values == candidate_id
        candidate_symbols = [str(symbol) for symbol in symbol_values[mask]]
        if candidate_symbols != expected_symbols:
            raise BatchedContractError(
                f"playbook {source_id!r} batched {field_name} symbols for candidate "
                f"{candidate_id!r} are misaligned"
            )
    return value


def _expected_candidate_ids(
    candidate_ids: Sequence[str],
    *,
    source_id: str,
) -> tuple[str, ...]:
    requested = tuple(candidate_ids)
    if not requested:
        raise BatchedContractError(f"playbook {source_id!r} requested candidate ids must not be empty")
    if len(set(requested)) != len(requested):
        raise BatchedContractError(f"playbook {source_id!r} requested candidate ids contain duplicates")
    return requested


def _requested_composed_candidates(
    candidate_ids: Sequence[str],
    *,
    candidates: Sequence[BatchedComposedCandidate],
    source_id: str,
) -> tuple[BatchedComposedCandidate, ...]:
    requested_ids = _expected_candidate_ids(candidate_ids, source_id=source_id)
    candidates_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    unknown = sorted(set(requested_ids) - set(candidates_by_id))
    if unknown:
        raise BatchedContractError(
            f"playbook {source_id!r} requested unknown candidate ids: {unknown}"
        )
    return tuple(candidates_by_id[candidate_id] for candidate_id in requested_ids)


def _diagnostics(result: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = result.get("diagnostics", {})
    if not isinstance(diagnostics, Mapping):
        raise TypeError("batched diagnostics must be a mapping")
    return dict(diagnostics)


def _validate_candidate_id(candidate_id: str, *, source_id: str, index: int) -> None:
    if not COMPONENT_ID_RE.fullmatch(candidate_id) or candidate_id in {".", ".."}:
        raise BatchedContractError(
            f"playbook {source_id!r} candidate_axis[{index}].candidate_id must contain only "
            "letters, numbers, dots, underscores, and hyphens"
        )
