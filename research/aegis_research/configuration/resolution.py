from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
    discover_component_registry,
)
from research.aegis_research.configuration.builders import (
    _build_strategy_run_lane_config,
    _build_train_lane_config,
)
from research.aegis_research.configuration.schema import (
    LANES,
    ConfigSelectionEvidence,
    ConfigValidationError,
    ConfigValidationIssue,
    LaneConfig,
    StrategyRunLaneConfig,
    TrainLaneConfig,
)
from research.aegis_research.configuration.secrets import redact_config, to_builtin
from research.aegis_research.configuration.validation import (
    _effective_run_mode,
    _validate_ranking,
    _validate_raw_lane_config,
    _validate_train_model_ref,
)
from research.aegis_research.model_registry import (
    FrozenModelRegistry,
    ModelRegistry,
    freeze_model_registry,
)
from research.aegis_research.metrics import (
    FrozenMetricRegistry,
    MetricRegistry,
    freeze_metric_registry,
    make_default_metric_registry,
)


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    keys: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise ConfigValidationError([ConfigValidationIssue(str(key), "duplicate mapping key")])
        keys.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class ResolvedLaneConfig:
    config: LaneConfig
    raw_config_hash: str
    authored_config: dict[str, Any]
    source_path: str | None = None
    component_registry: FrozenComponentRegistry | None = None
    model_registry: FrozenModelRegistry | None = None
    metric_registry: FrozenMetricRegistry | None = None
    selection: ConfigSelectionEvidence | None = None

    @property
    def lane(self) -> str:
        return self.config.lane

    def redacted_authored_config(self) -> dict[str, Any]:
        return redact_config(self.authored_config)

    def redacted_resolved_config(self) -> dict[str, Any]:
        return redact_config(to_builtin(asdict(self.config)))

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.config.schema_version,
            "lane": self.config.lane,
            "raw_config_hash": self.raw_config_hash,
            "source_path": self.source_path,
            "component_registry_fingerprint": (
                self.component_registry.fingerprint if self.component_registry else None
            ),
            "model_registry_fingerprint": (
                self.model_registry.fingerprint if self.model_registry else None
            ),
            "metric_registry_fingerprint": (
                self.metric_registry.fingerprint if self.metric_registry else None
            ),
            "selection": self.selection.manifest() if self.selection else None,
        }


def with_lane_config_selection(
    config: ResolvedLaneConfig,
    selection: ConfigSelectionEvidence,
    *,
    source_path: str | None = None,
) -> ResolvedLaneConfig:
    return ResolvedLaneConfig(
        config=config.config,
        raw_config_hash=config.raw_config_hash,
        authored_config=config.authored_config,
        source_path=config.source_path if source_path is None else source_path,
        component_registry=config.component_registry,
        model_registry=config.model_registry,
        metric_registry=config.metric_registry,
        selection=selection,
    )


def load_lane_config(
    path: str | Path,
    *,
    component_registry: FrozenComponentRegistry | None = None,
    model_registry: ModelRegistry | FrozenModelRegistry | None = None,
    metric_registry: MetricRegistry | FrozenMetricRegistry | None = None,
    expected_lane: str | None = None,
) -> ResolvedLaneConfig:
    config_path = Path(path)
    raw_text = config_path.read_text()
    raw = yaml.load(raw_text, Loader=_UniqueKeySafeLoader)
    return resolve_lane_config(
        raw,
        raw_text=raw_text,
        source_path=str(path),
        component_registry=component_registry,
        model_registry=model_registry,
        metric_registry=metric_registry,
        expected_lane=expected_lane,
    )


def resolve_lane_config(
    value: ResolvedLaneConfig | LaneConfig | dict[str, Any],
    *,
    raw_text: str | None = None,
    source_path: str | None = None,
    component_registry: FrozenComponentRegistry | None = None,
    model_registry: ModelRegistry | FrozenModelRegistry | None = None,
    metric_registry: MetricRegistry | FrozenMetricRegistry | None = None,
    expected_lane: str | None = None,
) -> ResolvedLaneConfig:
    frozen_model_registry = freeze_model_registry(model_registry)
    frozen_metric_registry = freeze_metric_registry(metric_registry)
    if isinstance(value, ResolvedLaneConfig):
        if expected_lane is not None and value.lane != expected_lane:
            raise ConfigValidationError(
                [ConfigValidationIssue("lane", f"must be {expected_lane!r}")]
            )
        effective_model_registry = (
            frozen_model_registry if model_registry is not None else value.model_registry
        )
        effective_metric_registry = (
            frozen_metric_registry or value.metric_registry or make_default_metric_registry()
        )
        if model_registry is None and metric_registry is None and value.metric_registry is not None:
            return value
        if model_registry is not None or metric_registry is not None:
            _assert_resolved_config_registries(
                value.config,
                frozen_model_registry=effective_model_registry,
                frozen_metric_registry=effective_metric_registry,
            )
        return ResolvedLaneConfig(
            config=value.config,
            raw_config_hash=value.raw_config_hash,
            authored_config=value.authored_config,
            source_path=value.source_path,
            component_registry=value.component_registry,
            model_registry=effective_model_registry,
            metric_registry=effective_metric_registry,
            selection=value.selection,
        )

    registry = component_registry or discover_component_registry()
    effective_metric_registry = frozen_metric_registry or make_default_metric_registry()
    if isinstance(value, StrategyRunLaneConfig | TrainLaneConfig):
        raw = to_builtin(asdict(value))
        raw_text = yaml.safe_dump(raw, sort_keys=False)
        return _build_resolved_lane_config(
            raw,
            raw_text=raw_text,
            source_path=source_path,
            component_registry=registry,
            model_registry=frozen_model_registry,
            metric_registry=effective_metric_registry,
            expected_lane=expected_lane,
        )

    return _build_resolved_lane_config(
        value,
        raw_text=raw_text,
        source_path=source_path,
        component_registry=registry,
        model_registry=frozen_model_registry,
        metric_registry=effective_metric_registry,
        expected_lane=expected_lane,
    )


def _build_resolved_lane_config(
    raw: dict[str, Any],
    *,
    raw_text: str | None,
    source_path: str | None,
    component_registry: FrozenComponentRegistry,
    model_registry: FrozenModelRegistry | None,
    metric_registry: FrozenMetricRegistry,
    expected_lane: str | None,
) -> ResolvedLaneConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError([ConfigValidationIssue("$", "lane config must be a mapping")])

    issues: list[ConfigValidationIssue] = []
    _validate_raw_lane_config(
        raw,
        issues,
        component_registry=component_registry,
        model_registry=model_registry,
        metric_registry=metric_registry,
        expected_lane=expected_lane,
    )
    if issues:
        raise ConfigValidationError(issues)

    lane = _effective_run_mode(raw, expected_lane)
    if lane == "run":
        config: LaneConfig = _build_strategy_run_lane_config(raw)
    elif lane == "train":
        config = _build_train_lane_config(raw)
    else:
        raise ConfigValidationError(
            [ConfigValidationIssue("lane", f"must be one of {sorted(LANES)}")]
        )

    text_for_hash = raw_text if raw_text is not None else yaml.safe_dump(raw, sort_keys=False)
    return ResolvedLaneConfig(
        config=config,
        raw_config_hash=hashlib.sha256(text_for_hash.encode()).hexdigest(),
        authored_config=to_builtin(raw),
        source_path=source_path,
        component_registry=component_registry,
        model_registry=model_registry,
        metric_registry=metric_registry,
    )


def _assert_resolved_config_registries(
    config: LaneConfig,
    *,
    frozen_model_registry: FrozenModelRegistry | None,
    frozen_metric_registry: FrozenMetricRegistry,
) -> None:
    issues: list[ConfigValidationIssue] = []
    if isinstance(config, TrainLaneConfig):
        if frozen_model_registry is not None:
            _validate_train_model_ref(
                "train.model",
                to_builtin(asdict(config.model)),
                issues,
                model_registry=frozen_model_registry,
            )
    elif isinstance(config, StrategyRunLaneConfig):
        _validate_ranking(
            "ranking",
            to_builtin(asdict(config.ranking)),
            issues,
            lane="run",
            registry=frozen_metric_registry,
        )
    if issues:
        raise ConfigValidationError(issues)
