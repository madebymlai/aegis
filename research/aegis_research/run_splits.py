from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration.schema import ConfigValidationIssue, RunSplitConfig
from research.aegis_research.data_schema import index_identity

SPLITTER_METHOD_PREFIX = "from_"
SPLITTER_INDEX_PARAM = "index"
RUN_SCORING_SET_POLICY = "exactly_two_sets_first_selection_second_held_out"
DENIED_SPLITTER_PARAMS = {
    "eval_times",
    "length_choice_func",
    "length_p_func",
    "pred_times",
    "template_context",
    "purged_splitter",
    "skl_splitter",
    "split_check_template",
    "split_func",
    "start_choice_func",
    "start_p_func",
}


@dataclass(frozen=True)
class SplitterParamInfo:
    name: str
    required: bool
    default: Any = None
    annotation: str | None = None
    kind: str = "positional_or_keyword"
    denied: bool = False

    def payload(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "required": self.required,
            "kind": self.kind,
            "denied": self.denied,
        }
        if self.annotation is not None:
            payload["annotation"] = self.annotation
        if not self.required:
            payload["default"] = _json_safe_default(self.default)
        return payload


@dataclass(frozen=True)
class RunSplit:
    label: str
    set_indices: dict[str, pd.Index]
    selection_set: str
    held_out_set: str

    @property
    def selection_index(self) -> pd.Index:
        return self.set_indices[self.selection_set]

    @property
    def held_out_index(self) -> pd.Index:
        return self.set_indices[self.held_out_set]


@dataclass(frozen=True)
class RunSplitsResult:
    splits: list[RunSplit]
    metadata: dict[str, Any]
    native_object: Any | None = None


@dataclass(frozen=True)
class SplitterMethodInfo:
    method: str
    params: tuple[SplitterParamInfo, ...]
    accepts_var_kwargs: bool

    @property
    def param_names(self) -> set[str]:
        return {param.name for param in self.params}

    @property
    def required_params(self) -> tuple[str, ...]:
        return tuple(param.name for param in self.params if param.required and not param.denied)

    @property
    def denied_params(self) -> tuple[str, ...]:
        return tuple(param.name for param in self.params if param.denied)

    @property
    def required_denied_params(self) -> tuple[str, ...]:
        return tuple(param.name for param in self.params if param.required and param.denied)

    @property
    def supported(self) -> bool:
        return not self.required_denied_params

    @property
    def unsupported_reason(self) -> str | None:
        if not self.required_denied_params:
            return None
        return "requires internal params that cannot be supplied from config: " f"{list(self.required_denied_params)}"

    def payload(self) -> dict[str, Any]:
        payload = {
            "method": self.method,
            "supported": self.supported,
            "run_scoring_set_policy": RUN_SCORING_SET_POLICY,
            "params": [param.payload() for param in self.params],
            "required_params": list(self.required_params),
            "denied_internal_params": list(self.denied_params),
            "required_internal_params": list(self.required_denied_params),
            "accepts_var_kwargs": self.accepts_var_kwargs,
        }
        if self.unsupported_reason is not None:
            payload["unsupported_reason"] = self.unsupported_reason
        return payload


def splitter_method_names() -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name in dir(vbt.Splitter)
            if name.startswith(SPLITTER_METHOD_PREFIX) and callable(getattr(vbt.Splitter, name))
        )
    )


def splitter_catalog_payload() -> dict[str, Any]:
    return {
        "schema_version": "splitter_catalog.v1",
        "source": "vectorbtpro.Splitter",
        "run_scoring_set_policy": RUN_SCORING_SET_POLICY,
        "methods": [splitter_method_info(method).payload() for method in splitter_method_names()],
    }


def splitter_method_info(method: str) -> SplitterMethodInfo:
    if method not in splitter_method_names():
        raise ValueError(f"unknown VBT splitter method: {method}")
    signature = inspect.signature(getattr(vbt.Splitter, method))
    seen_params: set[str] = set()
    params: list[SplitterParamInfo] = []
    accepts_var_kwargs = False
    for name, parameter in signature.parameters.items():
        if name in {"cls", SPLITTER_INDEX_PARAM}:
            continue
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            accepts_var_kwargs = True
            continue
        seen_params.add(name)
        required = parameter.default is inspect.Parameter.empty
        default = None if required else parameter.default
        params.append(
            SplitterParamInfo(
                name=name,
                required=required,
                default=default,
                annotation=_annotation_name(parameter.annotation),
                kind=parameter.kind.name.lower(),
                denied=name in DENIED_SPLITTER_PARAMS,
            )
        )
    if accepts_var_kwargs and method != "from_splits":
        params.extend(_forwarded_from_splits_params(seen_params))
    return SplitterMethodInfo(
        method=method,
        params=tuple(params),
        accepts_var_kwargs=accepts_var_kwargs,
    )


def _forwarded_from_splits_params(seen_params: set[str]) -> list[SplitterParamInfo]:
    signature = inspect.signature(vbt.Splitter.from_splits)
    forwarded: list[SplitterParamInfo] = []
    for name, parameter in signature.parameters.items():
        if name in {"cls", SPLITTER_INDEX_PARAM, "splits"} or name in seen_params:
            continue
        if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            continue
        required = parameter.default is inspect.Parameter.empty
        if required:
            continue
        forwarded.append(
            SplitterParamInfo(
                name=name,
                required=False,
                default=parameter.default,
                annotation=_annotation_name(parameter.annotation),
                kind=parameter.kind.name.lower(),
                denied=name in DENIED_SPLITTER_PARAMS,
            )
        )
    return forwarded


def validate_run_split_config(
    split: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    path: str = "split",
) -> None:
    method = split.get("method")
    if not isinstance(method, str) or not method:
        issues.append(ConfigValidationIssue(f"{path}.method", "must be a non-empty VBT splitter method"))
        return
    if method not in splitter_method_names():
        issues.append(
            ConfigValidationIssue(
                f"{path}.method",
                f"must be one of {list(splitter_method_names())}",
            )
        )
        return

    params = split.get("params", {})
    if not isinstance(params, dict):
        issues.append(ConfigValidationIssue(f"{path}.params", "must be a mapping"))
        return

    info = splitter_method_info(method)
    if info.required_denied_params:
        issues.append(
            ConfigValidationIssue(
                f"{path}.method",
                "requires internal params that cannot be supplied from config: "
                f"{list(info.required_denied_params)}",
            )
        )
        return
    for param_name in info.denied_params:
        if param_name in params:
            issues.append(
                ConfigValidationIssue(
                    f"{path}.params.{param_name}",
                    "is managed internally or cannot be safely supplied from config",
                )
            )
    for param_name in sorted(set(params) - info.param_names):
        issues.append(
            ConfigValidationIssue(
                f"{path}.params.{param_name}",
                f"is not an explicit parameter of vbt.Splitter.{method}",
            )
        )
    for param_name in info.required_params:
        if param_name not in params:
            issues.append(ConfigValidationIssue(f"{path}.params.{param_name}", "is required"))


def build_run_splits_result(index: pd.Index, config: RunSplitConfig) -> RunSplitsResult:
    splitter = _call_vbt_splitter(index, config)
    splits = _run_splits_from_index_slices(
        splitter.take(index, squeeze_one_split=False, squeeze_one_set=False)
    )
    if len(splits) > config.max_splits:
        raise ValueError(
            f"{config.method} produced {len(splits)} splits, exceeding split.max_splits"
        )
    resource_estimate = _resource_estimate(
        index,
        splits,
        max_public_artifact_bytes=config.max_public_artifact_bytes,
    )
    if resource_estimate["estimated_output_cells"] > config.max_estimated_output_cells:
        raise ValueError("split estimated output cells exceed split.max_estimated_output_cells")
    if resource_estimate["estimated_public_artifact_bytes"] > config.max_public_artifact_bytes:
        raise ValueError("split public evidence exceeds split.max_public_artifact_bytes")
    metadata = {
        "schema_version": "run_splits.v1",
        "method": config.method,
        "params": dict(config.params),
        "source_index": index_identity(index),
        "n_splits": len(splits),
        "set_usage_policy": RUN_SCORING_SET_POLICY,
        "resource_estimate": resource_estimate,
        "sets": _set_summary(),
        "splits": _split_membership_metadata(index, splits),
    }
    return RunSplitsResult(splits=splits, metadata=metadata, native_object=splitter)


def _call_vbt_splitter(index: pd.Index, config: RunSplitConfig) -> vbt.Splitter:
    method = getattr(vbt.Splitter, config.method)
    return method(index, **config.params)


def _run_splits_from_index_slices(index_slices: Any) -> list[RunSplit]:
    if not isinstance(index_slices.index, pd.MultiIndex):
        raise TypeError("VBT splitter output must produce exactly two sets per split")
    names = set(index_slices.index.names)
    if not {"split", "set"}.issubset(names):
        raise ValueError("VBT splitter output must include split and set index levels")
    splits: list[RunSplit] = []
    for split_label in index_slices.index.get_level_values("split").unique():
        set_indices: dict[str, pd.Index] = {}
        set_labels = list(index_slices.loc[split_label].index.get_level_values("set").unique())
        if len(set_labels) != 2:
            raise ValueError(
                f"Split {split_label} produced {len(set_labels)} sets; "
                "run split scoring requires exactly two sets"
            )
        for set_label in set_labels:
            member_index = index_slices.loc[(split_label, set_label)]
            if len(member_index) == 0:
                raise ValueError(f"Split {split_label} set {set_label!r} is empty")
            set_indices[str(set_label)] = member_index
        selection_set = str(set_labels[0])
        held_out_set = str(set_labels[1])
        if not set_indices[selection_set].intersection(set_indices[held_out_set]).empty:
            raise ValueError(f"Split {split_label} selection and held-out sets overlap")
        splits.append(
            RunSplit(
                label=f"split_{split_label}",
                set_indices=set_indices,
                selection_set=selection_set,
                held_out_set=held_out_set,
            )
        )
    return splits


def _set_summary() -> list[dict[str, Any]]:
    return [
        {"role": "selection", "position": 0},
        {"role": "held_out", "position": 1},
    ]


def _resource_estimate(
    index: pd.Index,
    splits: list[RunSplit],
    *,
    max_public_artifact_bytes: int,
) -> dict[str, int]:
    total_membership_entries = sum(
        len(member_index) for split in splits for member_index in split.set_indices.values()
    )
    return {
        "split_count": len(splits),
        "source_rows": len(index),
        "total_membership_entries": total_membership_entries,
        "estimated_output_cells": total_membership_entries,
        "estimated_public_artifact_bytes": total_membership_entries * 16,
        "max_public_artifact_bytes": max_public_artifact_bytes,
    }


def _split_membership_metadata(source_index: pd.Index, splits: list[RunSplit]) -> list[dict[str, Any]]:
    records = []
    for split in splits:
        sets = {
            "selection": {
                **index_identity(split.selection_index),
                "membership": _membership_representation(source_index, split.selection_index),
            },
            "held_out": {
                **index_identity(split.held_out_index),
                "membership": _membership_representation(source_index, split.held_out_index),
            },
        }
        records.append(
            {
                "label": split.label,
                "sets": sets,
            }
        )
    return records


def _membership_representation(source_index: pd.Index, member_index: pd.Index) -> dict[str, Any]:
    positions = source_index.get_indexer(member_index)
    if (positions < 0).any():
        raise ValueError("split membership contains rows outside the source index")
    if len(positions) == 0:
        return {"kind": "empty", "positions": []}
    if len(positions) == 1 or bool(((positions[1:] - positions[:-1]) == 1).all()):
        return {"kind": "range", "start": int(positions[0]), "stop": int(positions[-1]) + 1}
    return {"kind": "sparse_indices", "positions": [int(position) for position in positions]}


def _annotation_name(annotation: Any) -> str | None:
    if annotation is inspect.Parameter.empty:
        return None
    text = str(annotation)
    return text.replace("typing.", "tp.")


def _json_safe_default(value: Any) -> Any:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return repr(value)
    return value
