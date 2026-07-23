from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
    discover_component_registry,
)
from research.aegis_research.configuration.cross_checks import cross_check_registries
from research.aegis_research.configuration.schema import (
    ConfigValidationError,
    ConfigValidationIssue,
    RunConfig,
)
from research.aegis_research.configuration.validation import (
    _validate_run_config,
)
from research.aegis_research.metrics import (
    FrozenMetricRegistry,
    MetricRegistry,
    freeze_metric_registry,
    make_default_metric_registry,
    make_metric_registry_for,
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
    # Resolution always installs an effective registry; direct construction
    # gets the same default rather than admitting None.
    metric_registry: FrozenMetricRegistry = field(default_factory=make_default_metric_registry)

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
            "metric_registry_fingerprint": self.metric_registry.fingerprint,
        }


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
    value: Mapping[str, Any],
    *,
    raw_text: str | None = None,
    source_path: str | None = None,
    component_registry: FrozenComponentRegistry | None = None,
    metric_registry: MetricRegistry | FrozenMetricRegistry | None = None,
) -> ResolvedRunConfig:
    """Resolve a raw-mapping Run Config into a validated ``ResolvedRunConfig``.

    Non-mapping values raise ``ConfigValidationError``.
    """
    if not isinstance(value, Mapping):
        raise ConfigValidationError([ConfigValidationIssue("$", "run config must be a mapping")])

    raw = dict(value)
    config, issues = _validate_run_config(raw)
    if config is None:
        raise ConfigValidationError(issues)

    registry = component_registry or discover_component_registry()
    frozen_metric_registry = freeze_metric_registry(metric_registry)
    effective_metric_registry = frozen_metric_registry or make_metric_registry_for(
        _requested_metric_ids(config)
    )
    issues.extend(
        cross_check_registries(
            config,
            component_registry=registry,
            metric_registry=effective_metric_registry,
        )
    )
    if issues:
        raise ConfigValidationError(issues)

    return _build_resolved_run_config(
        config,
        raw,
        raw_text=raw_text,
        source_path=source_path,
        component_registry=registry,
        metric_registry=effective_metric_registry,
    )


def _requested_metric_ids(config: RunConfig) -> tuple[str, ...]:
    """Return the unique Metric IDs requested by a typed Run Config."""
    ids = [config.ranking.metric, *config.report.metrics]
    return tuple(dict.fromkeys(ids))


def _build_resolved_run_config(
    config: RunConfig,
    raw: dict[str, Any],
    *,
    raw_text: str | None,
    source_path: str | None,
    component_registry: FrozenComponentRegistry,
    metric_registry: FrozenMetricRegistry,
) -> ResolvedRunConfig:
    text_for_hash = raw_text if raw_text is not None else yaml.safe_dump(raw, sort_keys=False)
    return ResolvedRunConfig(
        config=config,
        raw_config_hash=hashlib.sha256(text_for_hash.encode()).hexdigest(),
        authored_config=to_builtin(raw),
        source_path=source_path,
        component_registry=component_registry,
        metric_registry=metric_registry,
    )
