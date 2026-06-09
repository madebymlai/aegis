from __future__ import annotations

import contextlib
import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import TypeAdapter, ValidationError

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.component_registry import (
    ComponentRegistryError,
    ComponentSelection,
    FrozenComponentRegistry,
    discover_component_registry,
)

if TYPE_CHECKING:
    from research.aegis_research.component_registry import ComponentDefinition
from research.aegis_research.configuration.builders import _build_run_config
from research.aegis_research.configuration.pydantic_adapter import (
    _apply_removed_fields,
    _validation_error_to_issues,
)
from research.aegis_research.configuration.schema import (
    PORTFOLIO_TARGET_SIZE_TYPES,
    ConfigSelectionEvidence,
    ConfigValidationError,
    ConfigValidationIssue,
    DataConfig,
    OptimizationConfig,
    PortfolioConfig,
    ReportConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
)
from research.aegis_research.configuration.validation import (
    _is_absolute_or_user_path,
    _validate_ranking,
    _validate_raw_run_config,
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

    issues: list[ConfigValidationIssue] = []

    # ── pydantic-ported sections: data, portfolio, report, optimization ─
    data_config = _validate_data_section(raw, issues)
    portfolio_config = _validate_portfolio_section(raw, issues)
    report_config = _validate_report_section(raw, issues)
    optimization_config = _validate_optimization_section(raw, issues)

    # ── pydantic-ported sections: strategy, indicators ──────────────────
    strategy_config = _validate_strategy_section(raw, issues)
    indicator_configs = _validate_indicators_section(raw, issues)

    # ── membership + output-contract checks (need the registry) ─────────
    strategy_definition, indicator_definitions = _validate_component_membership(
        strategy_config,
        indicator_configs,
        issues,
        component_registry=component_registry,
    )
    _validate_component_output_contract(strategy_definition, indicator_definitions, issues)

    # ── params validation (needs manifest param_names) ───────────────────
    _validate_component_params_for_definition(
        "strategy", strategy_config, strategy_definition, issues
    )
    for _i, (ind_config, (ind_path, ind_def)) in enumerate(
        zip(indicator_configs, indicator_definitions, strict=False)
    ):
        _validate_component_params_for_definition(
            ind_path, ind_config, ind_def, issues
        )

    # ── legacy (still-raw-dict) sections ─────────────────────────────────
    _validate_raw_run_config(
        raw,
        issues,
        component_registry=component_registry,
        metric_registry=metric_registry,
    )
    if issues:
        raise ConfigValidationError(issues)

    text_for_hash = raw_text if raw_text is not None else yaml.safe_dump(raw, sort_keys=False)
    return ResolvedRunConfig(
        config=_build_run_config(
            raw,
            data_config=data_config,
            portfolio_config=portfolio_config,
            report_config=report_config,
            optimization_config=optimization_config,
            strategy_config=strategy_config,
            indicator_configs=indicator_configs,
        ),
        raw_config_hash=hashlib.sha256(text_for_hash.encode()).hexdigest(),
        authored_config=to_builtin(raw),
        source_path=source_path,
        component_registry=component_registry,
        metric_registry=metric_registry,
    )


def _validate_data_section(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> DataConfig | None:
    """Pydantic validate/construct for data, plus post-pydantic path-security."""
    data_raw = raw.get("data", {})
    if not isinstance(data_raw, dict):
        if data_raw or "data" in raw:
            issues.append(ConfigValidationIssue("data", "must be a mapping"))
        return None

    try:
        config = TypeAdapter(DataConfig).validate_python(data_raw)
    except ValidationError as e:
        issues.extend(_validation_error_to_issues(e, section="data"))
        return None

    # Post-pydantic checks (not suitable for @model_validator):
    # - Source whitelist (programmatic construction uses internal sources).
    # - Path security (requires filesystem access).
    _validate_data_source_whitelist(config.source, issues)
    if config.source == "csv" and config.path:
        _validate_csv_path_security(config.path, issues)

    return config


def _validate_data_source_whitelist(
    source: str,
    issues: list[ConfigValidationIssue],
) -> None:
    """Reject sources outside the known local + remote VBT set."""
    from research.aegis_research.market_data.sources import (
        LOCAL_DATA_SOURCES,
        remote_data_sources,
    )

    supported = LOCAL_DATA_SOURCES | remote_data_sources()
    if source not in supported:
        issues.append(
            ConfigValidationIssue(
                "data.source",
                f"must be one of {sorted(supported)}",
            )
        )


def _validate_csv_path_security(
    path: str,
    issues: list[ConfigValidationIssue],
) -> None:
    """Reject absolute, user-home, and parent-traversal csv paths."""
    parts = (
        set(Path(path).parts)
        | set(PurePosixPath(path).parts)
        | set(PureWindowsPath(path).parts)
    )
    if _is_absolute_or_user_path(path) or ".." in parts:
        issues.append(
            ConfigValidationIssue(
                "data.path",
                "must be a relative path under the project root",
            )
        )


def _validate_portfolio_section(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> PortfolioConfig | None:
    """Tombstone prepass + pydantic validate/construct for portfolio."""
    portfolio_raw = raw.get("portfolio", {})
    if not isinstance(portfolio_raw, dict):
        issues.append(ConfigValidationIssue("portfolio", "must be a mapping"))
        return None

    # ── tombstone prepass (strips removed keys, appends bespoke messages) ─
    cleaned = _apply_removed_fields(
        portfolio_raw, "portfolio", PortfolioConfig.REMOVED_FIELDS, issues
    )
    # size_type has conditional messages (not a simple fixed text)
    if "size_type" in cleaned:
        st_value = cleaned.pop("size_type")
        if not isinstance(st_value, str):
            issues.append(
                ConfigValidationIssue("portfolio.size_type", "must be a string")
            )
        elif st_value in PORTFOLIO_TARGET_SIZE_TYPES:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.size_type",
                    PortfolioConfig._SIZE_TYPE_TOMBSTONES["target"],
                )
            )
        else:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.size_type",
                    PortfolioConfig._SIZE_TYPE_TOMBSTONES["other"],
                )
            )

    # ── pydantic validate + construct ────────────────────────────────────
    try:
        return TypeAdapter(PortfolioConfig).validate_python(cleaned)
    except ValidationError as e:
        issues.extend(_validation_error_to_issues(e, section="portfolio"))
        return None


def _validate_report_section(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> ReportConfig | None:
    """Pydantic validate/construct for report."""
    report_raw = raw.get("report", {})
    if not isinstance(report_raw, dict):
        # ``report_raw`` is falsy when the raw value is ``None`` (YAML ``report:``)
        # or an empty collection; the ``"report" in raw`` guard catches those so
        # every non-dict value that was explicitly set produces an issue.
        if report_raw or "report" in raw:
            issues.append(ConfigValidationIssue("report", "must be a mapping"))
        return None

    try:
        return TypeAdapter(ReportConfig).validate_python(report_raw)
    except ValidationError as e:
        issues.extend(_validation_error_to_issues(e, section="report"))
        return None


def _validate_optimization_section(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> OptimizationConfig | None:
    """Pydantic validate/construct for optimization, with split-method prepass."""
    optimization_raw = raw.get("optimization")
    if optimization_raw is None:
        return None
    if not isinstance(optimization_raw, dict):
        issues.append(ConfigValidationIssue("optimization", "must be a mapping"))
        return None

    # ── split-method prepass (VBT introspection, produces dotted paths) ──
    split_raw = optimization_raw.get("split")
    if isinstance(split_raw, dict):
        from research.aegis_research.run_splits import validate_run_split_config

        validate_run_split_config(split_raw, issues, path="optimization.split")

    # ── pydantic validate + construct ────────────────────────────────────
    try:
        return TypeAdapter(OptimizationConfig).validate_python(optimization_raw)
    except ValidationError as e:
        issues.extend(_validation_error_to_issues(e, section="optimization"))
        return None


def _validate_strategy_section(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> RunSourceRefConfig | None:
    """Pydantic validate/construct for strategy."""
    strategy_raw = raw.get("strategy")
    if not isinstance(strategy_raw, dict):
        issues.append(ConfigValidationIssue("strategy", "must be a mapping"))
        return None
    try:
        return TypeAdapter(RunSourceRefConfig).validate_python(strategy_raw)
    except ValidationError as e:
        issues.extend(_validation_error_to_issues(e, section="strategy"))
        return None


def _validate_indicators_section(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> list[RunIndicatorSourceConfig]:
    """Pydantic validate/construct for each indicator."""
    indicators_raw = raw.get("indicators")
    if not isinstance(indicators_raw, list):
        issues.append(ConfigValidationIssue("indicators", "must be a list"))
        return []

    adapter = TypeAdapter(RunIndicatorSourceConfig)
    configs: list[RunIndicatorSourceConfig] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(indicators_raw):
        if not isinstance(item, dict):
            issues.append(
                ConfigValidationIssue(f"indicators[{i}]", "must be a mapping")
            )
            # Still attempt pydantic validation so we get the structural issues
            # on a best-effort basis.
            with contextlib.suppress(ValidationError):
                adapter.validate_python(item)
            continue
        try:
            config = adapter.validate_python(item)
        except ValidationError as e:
            issues.extend(_validation_error_to_issues(e, section=f"indicators[{i}]"))
            continue
        if config.id in seen_ids:
            issues.append(
                ConfigValidationIssue(
                    f"indicators[{i}].id",
                    f"duplicates indicator component id {config.id!r}",
                )
            )
        seen_ids.add(config.id)
        configs.append(config)
    return configs


def _validate_component_membership(
    strategy_config: RunSourceRefConfig | None,
    indicator_configs: list[RunIndicatorSourceConfig],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> tuple[
    ComponentDefinition | None,
    tuple[tuple[str, ComponentDefinition], ...],
]:
    """Membership check: reject unregistered component ids.

    Also rejects ``id == "all"`` (must select one component).
    Returns the registry definitions needed for the output-contract cross-check.
    """

    strategy_definition: ComponentDefinition | None = None
    if strategy_config is not None:
        if strategy_config.id == "all":
            issues.append(
                ConfigValidationIssue("strategy.id", "must select one component id")
            )
        else:
            try:
                strategy_definition = component_registry.get(
                    ComponentSelection("strategies", strategy_config.id)
                )
            except ComponentRegistryError:
                issues.append(
                    ConfigValidationIssue(
                        "strategy.id", "unknown strategie component id"
                    )
                )

    indicator_definitions: list[tuple[str, ComponentDefinition]] = []
    for i, config in enumerate(indicator_configs):
        item_path = f"indicators[{i}]"
        if config.id == "all":
            issues.append(
                ConfigValidationIssue(
                    f"{item_path}.id", "must select one component id"
                )
            )
            continue
        try:
            definition = component_registry.get(
                ComponentSelection("indicators", config.id)
            )
        except ComponentRegistryError:
            issues.append(
                ConfigValidationIssue(
                    f"{item_path}.id", "unknown indicator component id"
                )
            )
            continue
        indicator_definitions.append((item_path, definition))
    return strategy_definition, tuple(indicator_definitions)


def _validate_component_output_contract(
    strategy_definition: ComponentDefinition | None,
    indicator_definitions: tuple[tuple[str, ComponentDefinition], ...],
    issues: list[ConfigValidationIssue],
) -> None:
    """Output-contract cross-check: strategy consumes outputs produced by indicators."""
    if strategy_definition is None:
        return
    produced: dict[str, str] = {}
    for path, definition in indicator_definitions:
        for output_name in getattr(definition.manifest, "output_names", ()):
            previous = produced.get(output_name)
            if previous is not None:
                issues.append(
                    ConfigValidationIssue(
                        f"{path}.id",
                        f"duplicates produced indicator output {output_name!r} from {previous}",
                    )
                )
                continue
            produced[output_name] = f"{path}.id"

    missing = sorted(
        set(getattr(strategy_definition.manifest, "consumes_outputs", ())) - set(produced)
    )
    if missing:
        issues.append(
            ConfigValidationIssue(
                "strategy.consumes_outputs",
                f"strategy consumes outputs not produced by configured indicators: {missing}",
            )
        )


def _validate_component_params_for_definition(
    path: str,
    config: RunSourceRefConfig | RunIndicatorSourceConfig | None,
    definition: ComponentDefinition | None,
    issues: list[ConfigValidationIssue],
) -> None:
    """Validate params against the manifest's param_names, defaults, and param_space_callable."""
    if config is None or definition is None:
        return
    param_names = tuple(getattr(definition.manifest, "param_names", ()))
    if not param_names and not config.params:
        return
    unknown = sorted(set(config.params) - set(param_names))
    if unknown:
        issues.append(
            ConfigValidationIssue(
                f"{path}.params",
                f"params must be declared by the component manifest; unknown: {unknown}",
            )
        )
        return
    if not param_names:
        return
    if getattr(definition.manifest, "param_space_callable", None):
        return
    provided = set(config.params)
    defaults = set(getattr(definition.manifest, "defaults", {}))
    missing = sorted(set(param_names) - provided - defaults)
    if missing:
        issues.append(
            ConfigValidationIssue(
                path,
                "must provide params, component defaults, or param_space_callable "
                f"for params {missing}",
            )
        )


def _assert_resolved_config_registries(
    config: RunConfig,
    *,
    frozen_metric_registry: FrozenMetricRegistry,
) -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_ranking(
        "ranking",
        to_builtin(config.ranking),
        issues,
        registry=frozen_metric_registry,
    )
    if issues:
        raise ConfigValidationError(issues)
