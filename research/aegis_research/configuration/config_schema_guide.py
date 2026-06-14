"""Run Config forward-contract authoring guide renderer.

Renders a curated markdown guide for an LLM (or human) author. The guide is a
hybrid template: field tables and literal catalogs are interpolated from the
validating pydantic models and code constants at render time; semantics prose
is hand-curated.

The rendered guide states the **forward contract**, not the raw pydantic model:
the prepass overlay (``optimization`` required, ``schema_version`` const 8,
data-source whitelist) is applied so the documented requiredness matches the
enforced requiredness (ADR-0019, ADR-0012).
"""

from __future__ import annotations

import dataclasses
import textwrap
from collections.abc import Sequence
from dataclasses import MISSING
from dataclasses import Field as DcField
from dataclasses import fields as dc_fields
from typing import Any, Literal, get_args, get_origin

from research.aegis_research.configuration.schema import (
    CONFIG_SCHEMA_VERSION,
    DATA_ARRAY_SHORTCUTS,
    DATA_QUALITY_DEGRADATIONS,
    DEFAULT_LOCK_ROLE,
    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
    LOCK_ROLES,
    MISSING_POLICIES,
    OHLCV_ARRAYS,
    OPTIMIZATION_EXECUTE_RESERVED_KEYS,
    OPTIMIZATION_SEARCH_POLICIES,
    PORTFOLIO_DIRECTIONS,
    PREPASS_CONST_FIELDS,
    PREPASS_REQUIRED_FIELDS,
    SIGNAL_EXECUTION_TIMINGS,
    SIGNAL_POLICIES,
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
    SymbolSpec,
)
from research.aegis_research.market_data.sources import (
    LOCAL_DATA_SOURCES,
    remote_data_sources,
)

# Forward-contract overlay (PREPASS_REQUIRED_FIELDS / PREPASS_CONST_FIELDS) is
# owned by schema.py and shared with the validation prepass, so the documented
# requiredness cannot fork from the enforced requiredness (ADR-0019).

GUIDE_SCHEMA_VERSION = "config_schema_guide.v1"
"""Payload schema version for the ``aerd show config-schema`` JSON envelope."""


def _allowed_data_sources() -> set[str]:
    return LOCAL_DATA_SOURCES | remote_data_sources()


# ── Nested type tree for rendering ────────────────────────────────────────────

# Each top-level RunConfig section maps to its pydantic dataclass type.
_SECTION_TYPES: dict[str, type[object] | list[type[object]]] = {
    "data": DataConfig,
    "data.quality": DataQualityConfig,
    "portfolio": PortfolioConfig,
    "strategy": RunSourceRefConfig,
    "indicators": [RunIndicatorSourceConfig],  # list item type
    "ranking": RankingConfig,
    "report": ReportConfig,
    "optimization": OptimizationConfig,
    "optimization.split": RunSplitConfig,
    "signal": SignalConfig,
    "lock": Lock,
}

# Text anchors for curated prose that reference CLI subcommands.
_SHOW_SPLITTERS = "`aerd show splitters <method>`"
_SHOW_COMPONENTS = "`aerd show components`"


# ── Public API ────────────────────────────────────────────────────────────────


def render_config_schema_guide() -> str:
    """Render the Run Config forward-contract authoring guide as markdown."""
    sections: list[str] = [
        _render_header(),
        _render_forward_contract(),
        _render_top_level_fields(),
        _render_data_section(),
        _render_portfolio_section(),
        _render_strategy_section(),
        _render_indicators_section(),
        _render_ranking_section(),
        _render_report_section(),
        _render_optimization_section(),
        _render_signal_section(),
        _render_lock_section(),
        _render_literal_catalogs(),
        _render_split_params_pointer(),
        _render_component_ids_pointer(),
        _render_example(),
    ]
    return "\n\n".join(sections) + "\n"


# ── Section renderers ─────────────────────────────────────────────────────────


def _render_header() -> str:
    return textwrap.dedent("""\
    # Run Config Forward Contract

    The YAML Run Config is the sole authoring surface for `aerd run`. This guide
    documents the **forward contract** — the exact shape `aerd run` accepts — not
    the raw pydantic model. Where the model has defaults or optional fields the
    forward contract overrides, the overridden rule is stated first.""")


def _render_forward_contract() -> str:
    """The prepass overlay: rules that amend the raw pydantic model."""
    lines = [
        "## Forward-Contract Overrides",
        "",
        "These rules amend the pydantic model for the forward contract. A config that",
        "satisfies the model alone but not these overrides is **rejected** by `aerd run`.",
        "",
    ]

    # schema_version const
    ver = PREPASS_CONST_FIELDS["schema_version"]
    lines.append(f"- **`schema_version`** — must be present and exactly `{ver}`.")

    # optimization required
    lines.append(
        f"- **`optimization`** — required. {FORWARD_OPTIMIZATION_REQUIRED_MESSAGE}"
    )

    # data source whitelist
    sources = sorted(_allowed_data_sources())
    lines.append(
        f"- **`data.source`** — must be one of: {', '.join(f'`{s}`' for s in sources)}."
    )

    # removed fields
    lines.append(
        "- **Removed fields** — `labeler`, `train`, `model`, and any key not listed "
        "in this guide are rejected as unknown."
    )

    # schema_version
    lines.append(
        f"\nThe accepted Run Config schema version is **{CONFIG_SCHEMA_VERSION}**. "
        "Older or newer schema versions are rejected. The `schema_version` field is "
        "required at the top level with this exact value."
    )

    return "\n".join(lines)


def _render_top_level_fields() -> str:
    """Top-level RunConfig fields (literal keys, not nested sections)."""
    lines = [
        "## Top-Level Fields",
        "",
        "| Field | Type | Required | Default / Const | Notes |",
        "|-------|------|----------|-----------------|-------|",
    ]

    for fdef in _walk_dataclass_fields(RunConfig):
        required = "yes" if fdef.is_required else "no"
        default = fdef.default_str or "—"

        if fdef.name in PREPASS_REQUIRED_FIELDS:
            required = "yes"
            if fdef.name == "optimization":
                default = f"*required* (model default `None` ignored; {FORWARD_OPTIMIZATION_REQUIRED_MESSAGE})"

        if fdef.name in PREPASS_CONST_FIELDS:
            required = "yes"
            default = f"*const* `{PREPASS_CONST_FIELDS[fdef.name]}`"

        notes = fdef.notes or "—"
        lines.append(f"| `{fdef.name}` | `{fdef.type_str}` | {required} | {default} | {notes} |")

    return "\n".join(lines)


def _render_data_section() -> str:
    return _render_nested_section(
        "data",
        title="### `data` (required)",
        tag="keyword-only (no silent default); requires explicit `arrays`",
        extra_lines=[
            f"**arrays shortcuts**: `OHLCV` expands to `{', '.join(OHLCV_ARRAYS)}`. "
            "Any VBT feature name works; no surrounding whitespace or control characters.",
            f"**Allowed sources**: {', '.join(f'`{s}`' for s in sorted(_allowed_data_sources()))}.",
            "",
            "**`symbols`** — each entry is a `{ticker, ccy}` record (a bare string ticker is "
            "rejected). `ccy` is the literal quote token declared inline beside the ticker — "
            "`EUR`, `USD`, or a minor unit such as `GBp` (pence). Currency is instrument "
            "identity and is never sniffed from the data provider. Prices are converted to "
            "`portfolio.base_currency` (default `EUR`) before indicators and the portfolio "
            "run; a non-base-currency leg additionally pays `portfolio.fx_conversion_cost` "
            "per trade.",
            "",
            _render_field_table(SymbolSpec),
            "",
            "<br>**`quality.allowed_degradations`**: ",
        ],
    )


def _render_portfolio_section() -> str:
    return _render_nested_section(
        "portfolio",
        title="### `portfolio` (required)",
        tag="keyword-only (no silent default); requires explicit `gross_cap` and `direction`",
    )


def _render_strategy_section() -> str:
    return _render_nested_section(
        "strategy",
        title="### `strategy` (required)",
        tag="references a single strategy Component by `id`",
    )


def _render_indicators_section() -> str:
    item_type = _SECTION_TYPES["indicators"]
    if isinstance(item_type, list):
        item_type = item_type[0]

    lines = [
        "### `indicators` (required)",
        "",
        "A list of indicator Component references. Each entry has:",
        "",
        _render_field_table(item_type),
        "",
        "Must contain at least one entry. Each `id` must be unique across the list. "
        f"Use {_SHOW_COMPONENTS} to discover available component IDs.",
    ]
    return "\n".join(lines)


def _render_ranking_section() -> str:
    return _render_nested_section(
        "ranking",
        title="### `ranking` (required)",
        tag="selects the metric and aggregation for candidate ranking",
    )


def _render_report_section() -> str:
    return _render_nested_section(
        "report",
        title="### `report` (optional)",
        tag="thresholds for the run report's gate outcomes",
    )


def _render_optimization_section() -> str:
    lines = [
        "### `optimization` (required per forward contract)",
        "",
        "**Note**: the raw model declares `optimization` optional but the forward "
        "contract requires it. Every run must declare an optimization section.",
        "",
    ]
    lines.append(_render_field_table(OptimizationConfig))
    lines.append("")

    # optimization.split
    lines.append("#### `optimization.split`")
    lines.append("")
    lines.append(_render_field_table(RunSplitConfig))
    lines.append("")
    lines.append(
        f"Split parameters depend on the `method`. Use {_SHOW_SPLITTERS} "
        "to see the parameter catalog for each method."
    )
    lines.append("")
    lines.append(
        "**`split.params.set_labels`** — forbidden. Set roles (`selection`, "
        "`held_out`) are assigned positionally by Aegis (set 0 = selection, "
        "set 1 = held_out) and are not configurable."
    )
    lines.append("")
    lines.append(
        "**`optimization.execute`** forwards raw `vbt.parameterized` engine "
        "kwargs only (e.g. chunking, engine, progress). The reserved keys below "
        "are managed by Aegis's optimization layer and must not be set here: "
        f"{', '.join(f'`{k}`' for k in sorted(OPTIMIZATION_EXECUTE_RESERVED_KEYS))}."
    )

    return "\n".join(lines)


def _render_signal_section() -> str:
    return _render_nested_section(
        "signal",
        title="### `signal` (optional)",
        tag="signal conversion policy between allocations and orders",
    )


def _render_lock_section() -> str:
    lines = [
        "### `lock` (optional)",
        "",
        "Reproduce a prior Candidate's parameters. Two forms:",
        "",
        "**Scalar handle** (copy-paste from run output):",
        "```yaml",
        "lock: run_id[:role]",
        "```",
        f"- `role` is one of: {', '.join(f'`{r}`' for r in LOCK_ROLES)}",
        f"- Default role: `{DEFAULT_LOCK_ROLE}` (bare `run_id` implies `run_id:{DEFAULT_LOCK_ROLE}`)",
        "",
        "**Mapping form** (exact reference):",
        "```yaml",
        "lock:",
        "  run_id: <run-id>",
        "  candidate_id: <role-or-candidate-key>",
        "```",
        "",
        "When `lock` is present, the run takes every Component's parameters from the "
        "locked Candidate rather than searching for new ones. The `optimization` "
        "section is still required but its `search` / `split` values are ignored.",
        "",
    ]
    lines.append(_render_field_table(Lock))
    return "\n".join(lines)


def _render_literal_catalogs() -> str:
    """Render all literal catalogs from code constants."""
    lines = ["## Literal Catalogs", ""]

    catalogs = [
        (
            "Portfolio Directions",
            PORTFOLIO_DIRECTIONS,
            "Valid values for `portfolio.direction`.",
        ),
        (
            "Optimization Search Policies",
            OPTIMIZATION_SEARCH_POLICIES,
            "Valid values for `optimization.search`.",
        ),
        (
            "Data-Array Shortcuts",
            dict(DATA_ARRAY_SHORTCUTS),
            "Top-level shortcuts that expand to feature-name groups. "
            f"E.g. `OHLCV` → `{', '.join(OHLCV_ARRAYS)}`.",
        ),
        (
            "Allowed Data-Quality Degradations",
            DATA_QUALITY_DEGRADATIONS,
            "Valid values for `data.quality.allowed_degradations`.",
        ),
        (
            "Lock Roles",
            set(LOCK_ROLES),
            "Representative roles for `lock` handle resolution.",
        ),
        (
            "Signal Policies",
            SIGNAL_POLICIES,
            "Valid values for `signal.policy`.",
        ),
        (
            "Signal Execution Timings",
            SIGNAL_EXECUTION_TIMINGS,
            "Valid values for `signal.execution_timing`.",
        ),
        (
            "Missing-Index / Missing-Columns Policies",
            MISSING_POLICIES,
            "Valid values for `data.missing_index` and `data.missing_columns`.",
        ),
        (
            "Reserved `optimization.execute` Keys",
            set(OPTIMIZATION_EXECUTE_RESERVED_KEYS),
            "Keys that must NOT appear under `optimization.execute`; "
            "managed by Aegis's optimization layer.",
        ),
    ]

    for title, values, description in catalogs:
        lines.append(f"### {title}")
        lines.append(f"*{description}*")
        lines.append("")
        if isinstance(values, dict):
            for k, v in values.items():
                if isinstance(v, tuple):
                    lines.append(f"- `{k}` → `{', '.join(v)}`")
                else:
                    lines.append(f"- `{k}` → `{v}`")
        else:
            for v in sorted(values, key=str):
                lines.append(f"- `{v}`")
        lines.append("")

    return "\n".join(lines)


def _render_split_params_pointer() -> str:
    return textwrap.dedent(f"""\
    ## Split Parameters

    The `optimization.split.method` field selects a VBT Splitter factory
    (`from_rolling`, `from_purged_kfold`, `from_purged_walkforward`, etc.),
    and `optimization.split.params` carries the keyword arguments for that factory.

    Use **{_SHOW_SPLITTERS}** to see the parameter catalog for a given method:
    which params are required, which have defaults, and which are denied.""")


def _render_component_ids_pointer() -> str:
    return textwrap.dedent(f"""\
    ## Component IDs

    `strategy.id` and each `indicators[].id` must reference a discovered
    Component. Use **{_SHOW_COMPONENTS}** to list all available component
    IDs, their inputs, outputs, and whether they expose a searchable
    `param_space`.""")


def _render_example() -> str:
    """Embed a complete example Run Config YAML snippet."""
    return textwrap.dedent(f"""\
    ## Example Run Config

    A minimal, self-contained Run Config that exercises every required section:

    ```yaml
    schema_version: {CONFIG_SCHEMA_VERSION}
    name: example.run

    data:
      source: synthetic
      symbols:
        - {{ticker: A, ccy: EUR}}
        - {{ticker: B, ccy: EUR}}
        - {{ticker: C, ccy: EUR}}
      rows: 250
      arrays: [OHLCV]

    portfolio:
      gross_cap: 1.0
      direction: longonly
      base_currency: EUR

    strategy:
      id: demo.strategy

    indicators:
      - id: demo.returns

    ranking:
      metric: sharpe_ratio

    optimization:
      search: grid
      split:
        method: from_rolling
        params:
          length: 126
          split: 0.5
        max_splits: 2
    ```

    This example uses `synthetic` data (no network), the `demo.strategy` and
    `demo.returns` Component fixtures, and a tiny 2-split rolling window so
    it completes in seconds. The `demo.*` Components must exist under
    `research/components/strategies/` and `research/components/indicators/`
    relative to the working directory.""")


# ── Field-tree helpers ────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class FieldDef:
    """Flattened field metadata for rendering."""

    name: str
    type_str: str
    is_required: bool
    default_str: str | None
    notes: str | None = None


def _walk_dataclass_fields(cls: Any) -> list[FieldDef]:
    """Walk a pydantic dataclass and return flattened field definitions.

    Excludes internal/sentinel fields (names starting with underscore).
    """
    result: list[FieldDef] = []
    for f in dc_fields(cls):
        if f.name.startswith("_"):
            continue
        result.append(_field_def(f))
    return result


def _field_def(field: DcField[Any]) -> FieldDef:
    name = field.name
    annotation = field.type

    # Unwrap typing constructs
    type_str = _render_type(annotation)

    has_default = field.default is not MISSING
    has_factory = field.default_factory is not MISSING
    is_required = not has_default and not has_factory
    default_str = None

    if has_factory:
        try:
            val = field.default_factory()  # type: ignore[misc]
            default_str = _format_default(val)
        except Exception:
            default_str = "(factory)"
    elif has_default:
        default_str = _format_default(field.default)

    return FieldDef(
        name=name,
        type_str=type_str,
        is_required=is_required,
        default_str=default_str,
    )


def _render_type(annotation: Any) -> str:
    """Render a type annotation as a human-readable string."""
    origin = get_origin(annotation)

    # Optional[X] / X | None
    if _is_optional(annotation):
        args = get_args(annotation)
        inner = next((a for a in args if a is not type(None)), args[0])
        return f"{_render_type(inner)} | None"

    # Literal[...] — show enum-like values
    if origin is Literal:
        args = get_args(annotation)
        if all(isinstance(a, str) for a in args):
            return " | ".join(f'"{a}"' for a in args)
        return " | ".join(str(a) for a in args)

    # list[X] / Sequence[X]
    if origin in (list, Sequence):
        args = get_args(annotation)
        if args:
            return f"list[{_render_type(args[0])}]"
        return "list"

    # dict[str, X]
    if origin is dict:
        args = get_args(annotation)
        if args and len(args) == 2:
            return f"dict[{_render_type(args[0])}, {_render_type(args[1])}]"
        return "dict"

    # Annotated[X, ...] — unwrap to X
    if origin is not None and hasattr(origin, "__name__"):
        # Custom generic or Annotated
        if origin.__name__ == "Annotated":
            args = get_args(annotation)
            if args:
                return _render_type(args[0])
        return origin.__name__

    # Plain type
    if hasattr(annotation, "__name__"):
        return annotation.__name__

    return str(annotation)


def _is_optional(annotation: Any) -> bool:
    """True if the annotation is Optional[X] or X | None."""
    origin = get_origin(annotation)
    if origin is not None and origin.__name__ == "UnionType":
        args = get_args(annotation)
        return type(None) in args
    return False


def _format_default(value: Any) -> str:
    """Format a default value for display."""
    if value is None:
        return "`None`"
    if isinstance(value, str):
        return f'`"{value}"`'
    if isinstance(value, bool):
        return f"`{value}`"
    if isinstance(value, (int, float)):
        return f"`{value}`"
    # Collections, dataclass instances, etc.
    return f"`{value!r}`"


# ── Section-level renderer ────────────────────────────────────────────────────


def _render_nested_section(
    section_key: str,
    *,
    title: str,
    tag: str,
    extra_lines: Sequence[str] = (),
) -> str:
    """Render a section with its field table and optional extra lines."""
    cls = _SECTION_TYPES.get(section_key)
    if cls is None:
        return f"{title}\n\n*(no model metadata available)*"

    if isinstance(cls, list):
        cls = cls[0]

    lines = [title, "", f"*{tag}*", "", _render_field_table(cls)]

    quality_cls = _SECTION_TYPES.get(f"{section_key}.quality")
    if quality_cls is not None and not isinstance(quality_cls, list):
        lines.extend(["", "**`quality` sub-section:**", "", _render_field_table(quality_cls)])

    if extra_lines:
        lines.extend(extra_lines)

    return "\n".join(lines)


def _render_field_table(cls: type[object]) -> str:
    """Render a single pydantic dataclass as a field markdown table."""
    rows = [
        "| Field | Type | Required | Default | Notes |",
        "|-------|------|----------|---------|-------|",
    ]
    for fdef in _walk_dataclass_fields(cls):
        name = fdef.name
        type_str = fdef.type_str
        required = "yes" if fdef.is_required else "no"
        default = fdef.default_str or "—"
        notes = fdef.notes or "—"
        rows.append(f"| `{name}` | `{type_str}` | {required} | {default} | {notes} |")
    return "\n".join(rows)
