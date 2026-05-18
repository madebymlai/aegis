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
    _build_data_config,
    _build_indicator_config,
    _build_label_config,
    _build_play_lane_config,
    _build_strategy_run_lane_config,
    _build_train_lane_config,
)
from research.aegis_research.configuration.schema import (
    LANES,
    ConfigSelectionEvidence,
    ConfigValidationError,
    ConfigValidationIssue,
    ExperimentConfig,
    LaneConfig,
    ModelConfig,
    PlayLaneConfig,
    PortfolioConfig,
    ReportConfig,
    SignalConfig,
    SplitConfig,
    StrategyRunLaneConfig,
    TrainLaneConfig,
)
from research.aegis_research.configuration.secrets import redact_config, to_builtin
from research.aegis_research.configuration.validation import (
    _assert_model_config_registered,
    _validate_raw_config,
    _validate_raw_lane_config,
)
from research.aegis_research.model_registry import (
    FrozenModelRegistry,
    ModelRegistry,
    freeze_model_registry,
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
class ResolvedExperimentConfig:
    config: ExperimentConfig
    raw_config_hash: str
    authored_config: dict[str, Any]
    source_path: str | None = None
    model_registry: FrozenModelRegistry | None = None
    selection: ConfigSelectionEvidence | None = None

    def redacted_authored_config(self) -> dict[str, Any]:
        return redact_config(self.authored_config)

    def redacted_resolved_config(self) -> dict[str, Any]:
        return redact_config(to_builtin(asdict(self.config)))

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.config.schema_version,
            "raw_config_hash": self.raw_config_hash,
            "source_path": self.source_path,
            "selection": self.selection.manifest() if self.selection else None,
        }


@dataclass(frozen=True)
class ResolvedLaneConfig:
    config: LaneConfig
    raw_config_hash: str
    authored_config: dict[str, Any]
    source_path: str | None = None
    component_registry: FrozenComponentRegistry | None = None

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
        }


def with_config_selection(
    config: ResolvedExperimentConfig,
    selection: ConfigSelectionEvidence,
    *,
    source_path: str | None = None,
) -> ResolvedExperimentConfig:
    return ResolvedExperimentConfig(
        config=config.config,
        raw_config_hash=config.raw_config_hash,
        authored_config=config.authored_config,
        source_path=config.source_path if source_path is None else source_path,
        model_registry=config.model_registry,
        selection=selection,
    )


def load_experiment_config(
    path: str | Path,
    *,
    model_registry: ModelRegistry | FrozenModelRegistry | None = None,
) -> ResolvedExperimentConfig:
    config_path = Path(path)
    raw_text = config_path.read_text()
    raw = yaml.load(raw_text, Loader=_UniqueKeySafeLoader)
    return resolve_experiment_config(
        raw,
        raw_text=raw_text,
        source_path=str(path),
        model_registry=model_registry,
    )


def resolve_experiment_config(
    value: ResolvedExperimentConfig | ExperimentConfig | dict[str, Any],
    *,
    raw_text: str | None = None,
    source_path: str | None = None,
    model_registry: ModelRegistry | FrozenModelRegistry | None = None,
) -> ResolvedExperimentConfig:
    frozen_registry = freeze_model_registry(model_registry)
    if isinstance(value, ResolvedExperimentConfig):
        if frozen_registry is not None:
            _assert_model_config_registered(value.config.model, frozen_registry)
            return ResolvedExperimentConfig(
                config=value.config,
                raw_config_hash=value.raw_config_hash,
                authored_config=value.authored_config,
                source_path=value.source_path,
                model_registry=frozen_registry,
                selection=value.selection,
            )
        return value

    if isinstance(value, ExperimentConfig):
        raw = to_builtin(asdict(value))
        raw_text = yaml.safe_dump(raw, sort_keys=False)
        return _build_resolved_config(
            raw,
            raw_text=raw_text,
            source_path=source_path,
            model_registry=frozen_registry,
        )

    return _build_resolved_config(
        value,
        raw_text=raw_text,
        source_path=source_path,
        model_registry=frozen_registry,
    )


def load_lane_config(
    path: str | Path,
    *,
    component_registry: FrozenComponentRegistry | None = None,
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
        expected_lane=expected_lane,
    )


def resolve_lane_config(
    value: ResolvedLaneConfig | LaneConfig | dict[str, Any],
    *,
    raw_text: str | None = None,
    source_path: str | None = None,
    component_registry: FrozenComponentRegistry | None = None,
    expected_lane: str | None = None,
) -> ResolvedLaneConfig:
    if isinstance(value, ResolvedLaneConfig):
        if expected_lane is not None and value.lane != expected_lane:
            raise ConfigValidationError(
                [ConfigValidationIssue("lane", f"must be {expected_lane!r}")]
            )
        return value

    registry = component_registry or discover_component_registry()
    if isinstance(value, PlayLaneConfig | StrategyRunLaneConfig | TrainLaneConfig):
        raw = to_builtin(asdict(value))
        raw_text = yaml.safe_dump(raw, sort_keys=False)
        return _build_resolved_lane_config(
            raw,
            raw_text=raw_text,
            source_path=source_path,
            component_registry=registry,
            expected_lane=expected_lane,
        )

    return _build_resolved_lane_config(
        value,
        raw_text=raw_text,
        source_path=source_path,
        component_registry=registry,
        expected_lane=expected_lane,
    )


def _build_resolved_config(
    raw: dict[str, Any],
    *,
    raw_text: str | None,
    source_path: str | None,
    model_registry: FrozenModelRegistry | None,
) -> ResolvedExperimentConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError(
            [ConfigValidationIssue("$", "experiment config must be a mapping")]
        )

    issues: list[ConfigValidationIssue] = []
    _validate_raw_config(raw, issues, model_registry=model_registry)
    if issues:
        raise ConfigValidationError(issues)

    config = ExperimentConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        data=_build_data_config(raw.get("data", {})),
        indicators=_build_indicator_config(raw.get("indicators", {})),
        labels=_build_label_config(raw.get("labels", {})),
        split=SplitConfig(**raw.get("split", {})),
        model=ModelConfig(**raw.get("model", {})),
        signals=SignalConfig(**raw.get("signals", {})),
        portfolio=PortfolioConfig(**raw.get("portfolio", {})),
        report=ReportConfig(**raw.get("report", {})),
        output_dir=raw.get("output_dir", "runs"),
    )
    text_for_hash = raw_text if raw_text is not None else yaml.safe_dump(raw, sort_keys=False)
    return ResolvedExperimentConfig(
        config=config,
        raw_config_hash=hashlib.sha256(text_for_hash.encode()).hexdigest(),
        authored_config=to_builtin(raw),
        source_path=source_path,
        model_registry=model_registry,
        selection=None,
    )


def _build_resolved_lane_config(
    raw: dict[str, Any],
    *,
    raw_text: str | None,
    source_path: str | None,
    component_registry: FrozenComponentRegistry,
    expected_lane: str | None,
) -> ResolvedLaneConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError([ConfigValidationIssue("$", "lane config must be a mapping")])

    issues: list[ConfigValidationIssue] = []
    _validate_raw_lane_config(
        raw,
        issues,
        component_registry=component_registry,
        expected_lane=expected_lane,
    )
    if issues:
        raise ConfigValidationError(issues)

    lane = str(raw["lane"])
    if lane == "play":
        config: LaneConfig = _build_play_lane_config(raw)
    elif lane == "run":
        config = _build_strategy_run_lane_config(raw)
    elif lane == "train":
        config = _build_train_lane_config(raw)
    else:
        raise ConfigValidationError([ConfigValidationIssue("lane", f"must be one of {sorted(LANES)}")])

    text_for_hash = raw_text if raw_text is not None else yaml.safe_dump(raw, sort_keys=False)
    return ResolvedLaneConfig(
        config=config,
        raw_config_hash=hashlib.sha256(text_for_hash.encode()).hexdigest(),
        authored_config=to_builtin(raw),
        source_path=source_path,
        component_registry=component_registry,
    )
