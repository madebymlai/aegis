from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
    discover_component_registry,
)
from research.aegis_research.configuration.schema import (
    ConfigSelectionEvidence,
    ConfigValidationError,
    ConfigValidationIssue,
    RunConfig,
)
from research.aegis_research.configuration.validation import (
    validate_run_config,
    _post_validate_ranking_metric as _check_ranking_metric_membership,
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
class ResolvedRunConfig:
    config: RunConfig
    raw_config_hash: str
    authored_config: dict[str, Any]
    source_path: str | None = None
    component_registry: FrozenComponentRegistry | None = None
    metric_registry: FrozenMetricRegistry | None = None
    selection: ConfigSelectionEvidence | None = None

    def authored_config_document(self) -> dict[str, Any]:
        return self.authored_config

    def resolved_config_document(self) -> dict[str, Any]:
        return to_builtin(self.config)

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.config.schema_version,
            "raw_config_hash": self.raw_config_hash,
            "source_path": self.source_path,
            "component_registry_fingerprint": (
                self.component_registry.fingerprint if self.component_registry else None
            ),
            "metric_registry_fingerprint": (
                self.metric_registry.fingerprint if self.metric_registry else None
            ),
            "selection": self.selection.manifest() if self.selection else None,
        }


def with_run_config_selection(
    config: ResolvedRunConfig,
    selection: ConfigSelectionEvidence,
    *,
    source_path: str | None = None,
) -> ResolvedRunConfig:
    return ResolvedRunConfig(
        config=config.config,
        raw_config_hash=config.raw_config_hash,
        authored_config=config.authored_config,
        source_path=config.source_path if source_path is None else source_path,
        component_registry=config.component_registry,
        metric_registry=config.metric_registry,
        selection=selection,
    )


def load_run_config(
    path: str | Path,
    *,
    component_registry: FrozenComponentRegistry | None = None,
    metric_registry: MetricRegistry | FrozenMetricRegistry | None = None,
) -> ResolvedRunConfig:
    config_path = Path(path)
    raw_text = config_path.read_text()
    raw = yaml.load(raw_text, Loader=_UniqueKeySafeLoader)
    return resolve_run_config(
        raw,
        raw_text=raw_text,
        source_path=str(path),
        component_registry=component_registry,
        metric_registry=metric_registry,
    )


def resolve_run_config(
    value: ResolvedRunConfig | RunConfig | dict[str, Any],
    *,
    raw_text: str | None = None,
    source_path: str | None = None,
    component_registry: FrozenComponentRegistry | None = None,
    metric_registry: MetricRegistry | FrozenMetricRegistry | None = None,
) -> ResolvedRunConfig:
    frozen_metric_registry = freeze_metric_registry(metric_registry)
    if isinstance(value, ResolvedRunConfig):
        effective_metric_registry = (
            frozen_metric_registry or value.metric_registry or make_default_metric_registry()
        )
        if metric_registry is None and value.metric_registry is not None:
            return value
        if metric_registry is not None:
            _assert_resolved_config_registries(
                value.config,
                frozen_metric_registry=effective_metric_registry,
            )
        return ResolvedRunConfig(
            config=value.config,
            raw_config_hash=value.raw_config_hash,
            authored_config=value.authored_config,
            source_path=value.source_path,
            component_registry=value.component_registry,
            metric_registry=effective_metric_registry,
            selection=value.selection,
        )

    registry = component_registry or discover_component_registry()
    effective_metric_registry = frozen_metric_registry or make_default_metric_registry()
    if isinstance(value, RunConfig):
        raw = to_builtin(value)
        raw_text = yaml.safe_dump(raw, sort_keys=False)
        return _build_resolved_run_config(
            raw,
            raw_text=raw_text,
            source_path=source_path,
            component_registry=registry,
            metric_registry=effective_metric_registry,
        )

    return _build_resolved_run_config(
        value,
        raw_text=raw_text,
        source_path=source_path,
        component_registry=registry,
        metric_registry=effective_metric_registry,
    )


def _build_resolved_run_config(
    raw: dict[str, Any],
    *,
    raw_text: str | None,
    source_path: str | None,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> ResolvedRunConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError([ConfigValidationIssue("$", "run config must be a mapping")])

    config, issues = validate_run_config(
        raw,
        component_registry=component_registry,
        metric_registry=metric_registry,
    )
    if issues:
        raise ConfigValidationError(issues)

    text_for_hash = raw_text if raw_text is not None else yaml.safe_dump(raw, sort_keys=False)
    return ResolvedRunConfig(
        config=config,  # type: ignore[arg-type]  # guaranteed non-None when issues is empty
        raw_config_hash=hashlib.sha256(text_for_hash.encode()).hexdigest(),
        authored_config=to_builtin(raw),
        source_path=source_path,
        component_registry=component_registry,
        metric_registry=metric_registry,
    )


def _assert_resolved_config_registries(
    config: RunConfig,
    *,
    frozen_metric_registry: FrozenMetricRegistry,
) -> None:
    issues: list[ConfigValidationIssue] = []
    _check_ranking_metric_membership(
        config.ranking.metric,
        issues,
        registry=frozen_metric_registry,
    )
    if issues:
        raise ConfigValidationError(issues)
