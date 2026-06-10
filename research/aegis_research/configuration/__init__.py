"""Public config surface — single import home for all configuration names.

All public configuration types, constants, and entry points are re-exported
here.  Internal implementation modules (cross_checks, field_types, etc.) are
package-private and not part of this surface.
"""

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.configuration.env_references import resolve_env_refs
from research.aegis_research.configuration.field_types import (
    ComponentIdStr,
    NonEmptyStr,
)
from research.aegis_research.configuration.resolution import (
    ResolvedRunConfig,
    load_run_config,
    resolve_run_config,
    with_run_config_selection,
)
from research.aegis_research.configuration.schema import (
    CONFIG_SCHEMA_VERSION,
    DATA_ARRAY_SHORTCUTS,
    DATA_QUALITY_DEGRADATIONS,
    DEFAULT_LOCK_ROLE,
    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
    IDENTIFIER_RE,
    LOCK_ROLES,
    MISSING_POLICIES,
    OHLCV_ARRAYS,
    OPTIMIZATION_SEARCH_POLICIES,
    PORTFOLIO_DIRECTIONS,
    SIGNAL_EXECUTION_TIMINGS,
    SIGNAL_POLICIES,
    ConfigSelectionEvidence,
    ConfigValidationError,
    ConfigValidationIssue,
    DataConfig,
    DataQualityConfig,
    Lock,
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    RunSplitConfig,
    SignalConfig,
    expand_data_arrays,
    has_data_array_token_shape,
    merge_data_arrays,
)
from research.aegis_research.market_data.sources import (
    LOCAL_DATA_SOURCES,
    data_sources,
    remote_data_sources,
)

DATA_SOURCES = data_sources()
REMOTE_DATA_SOURCES = remote_data_sources()

__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "DATA_ARRAY_SHORTCUTS",
    "DATA_QUALITY_DEGRADATIONS",
    "DATA_SOURCES",
    "DEFAULT_LOCK_ROLE",
    "FORWARD_OPTIMIZATION_REQUIRED_MESSAGE",
    "IDENTIFIER_RE",
    "LOCAL_DATA_SOURCES",
    "LOCK_ROLES",
    "MISSING_POLICIES",
    "OHLCV_ARRAYS",
    "OPTIMIZATION_SEARCH_POLICIES",
    "PORTFOLIO_DIRECTIONS",
    "REMOTE_DATA_SOURCES",
    "SIGNAL_EXECUTION_TIMINGS",
    "SIGNAL_POLICIES",
    "ComponentIdStr",
    "ConfigSelectionEvidence",
    "ConfigValidationError",
    "ConfigValidationIssue",
    "DataConfig",
    "DataQualityConfig",
    "Lock",
    "NonEmptyStr",
    "OptimizationConfig",
    "PortfolioConfig",
    "RankingConfig",
    "ReportConfig",
    "ResolvedRunConfig",
    "RunConfig",
    "RunIndicatorSourceConfig",
    "RunSourceRefConfig",
    "RunSplitConfig",
    "SignalConfig",
    "expand_data_arrays",
    "has_data_array_token_shape",
    "load_run_config",
    "merge_data_arrays",
    "resolve_env_refs",
    "resolve_run_config",
    "to_builtin",
    "with_run_config_selection",
]
