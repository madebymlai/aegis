"""Run Config forward-contract authoring guide renderer.

Renders a curated markdown guide for an LLM (or human) author. The guide is a
hybrid template: field tables and literal catalogs are interpolated from the
validating pydantic models and code constants at render time; semantics prose
is hand-curated.

The validating model is the structural authoring contract. Curated prose adds
domain semantics that field metadata cannot express (ADR-0019, ADR-0012).
"""

from __future__ import annotations

import dataclasses
import textwrap
from collections.abc import Sequence
from dataclasses import MISSING
from dataclasses import Field as DcField
from dataclasses import fields as dc_fields
from typing import Any, Literal, get_args, get_origin, get_type_hints

from pydantic import TypeAdapter

from research.aegis_research.configuration.schema import (
    CONFIG_SCHEMA_VERSION,
    DATA_ARRAY_SHORTCUTS,
    DEFAULT_LOCK_ROLE,
    LOCK_ROLES,
    MISSING_POLICIES,
    OHLCV_ARRAYS,
    OPTIMIZATION_SEARCH_POLICIES,
    PORTFOLIO_DIRECTIONS,
    SIGNAL_EXECUTION_TIMINGS,
    SIGNAL_POLICIES,
    DataConfig,
    Lock,
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    SignalConfig,
)

GUIDE_SCHEMA_VERSION = "config_schema_guide.v1"
"""Payload schema version for the ``aerd show config-schema`` JSON envelope."""


# ── Nested type tree for rendering ────────────────────────────────────────────

# Each top-level RunConfig section maps to its pydantic dataclass type.
_SECTION_TYPES: dict[str, type[object] | list[type[object]]] = {
    "data": DataConfig,
    "portfolio": PortfolioConfig,
    "strategy": RunSourceRefConfig,
    "indicators": [RunIndicatorSourceConfig],  # list item type
    "ranking": RankingConfig,
    "report": ReportConfig,
    "optimization": OptimizationConfig,
    "signal": SignalConfig,
    "lock": Lock,
}

# Text anchors for curated prose that reference CLI subcommands.
_SHOW_COMPONENTS = "`aerd show components`"

# ── Public API ────────────────────────────────────────────────────────────────


def render_config_schema_guide() -> str:
    """Render the Run Config forward-contract authoring guide as markdown."""
    sections: list[str] = [
        _render_header(),
        _render_structural_contract(),
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
        _render_component_ids_pointer(),
        _render_example(),
        _render_futures_example(),
    ]
    return "\n\n".join(sections) + "\n"


# ── Section renderers ─────────────────────────────────────────────────────────


def _render_header() -> str:
    return textwrap.dedent("""\
    # Run Config Forward Contract

    The YAML Run Config is the sole authoring surface for `aerd run`. This guide
    documents the exact structural shape `aerd run` accepts. Requiredness and
    literal constraints come from the validating pydantic model.""")


def _render_structural_contract() -> str:
    """Render top-level structural rules and removed authoring fields."""
    lines = [
        "## Structural Contract",
    ]

    # removed fields
    lines.append(
        "- **Removed fields** — `data.source`, `data.symbols`, `data.provider`, "
        "`data.fx_provider`, `labeler`, `train`, `model`, and any key not listed in "
        "this guide are rejected as unknown."
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
            "",
            "**`instruments`** — tradeable native Nautilus `InstrumentId` values in execution "
            "column order. These are parsed to `InstrumentId` at the catalog adapter edge and "
            "remain typed through the runtime bundle. An entry may carry an optional declared "
            "mark-mode token — `UEQC.IBIS:QUOTE` (quote-marked: BID/ASK bars, derived mid) or "
            "`:MID` (bar-marked midpoint). Absent means LAST — no heuristic, so a *tradeable* "
            "cash FX pair must declare `:MID` explicitly. Parsed once at config load into "
            "`mark_modes`.",
            "",
            "**`exchange`** — optional data-only native `InstrumentId` values requested from "
            "the same catalog/port but never exposed as tradeable bundle columns. Section "
            "membership is itself a mark declaration: a conversion leg is bar-marked MID "
            "(IBKR serves no TRADES print for cash FX), so it takes no token.",
            "",
            "**`futures`** — optional bare continuous-future root symbols (e.g. `[ES, KC]`), "
            "not native ids. Each is materialised on demand as a back-adjusted continuous "
            "series (Path A); venue and quote currency are catalog-authoritative from its "
            "dated legs. A run needs at least one of `instruments` or `futures`.",
            "",
        ],
    )


def _render_portfolio_section() -> str:
    return _render_nested_section(
        "portfolio",
        title="### `portfolio` (required)",
        tag="keyword-only (no silent default); requires explicit `direction` — the "
        "exposure envelope is the fixed unit-gross sleeve contract, not config",
        extra_lines=[
            "**`band_up` / `band_down`** — sleeve-wide no-trade band widths. "
            "`band_up` gates trims and `band_down` gates adds. Defaults are zero, "
            "which means rebalance every executable bar.",
            "",
            "**`band_overrides`** — optional per-tradeable override map. Keys are "
            "native `data.instruments` ids (for example `AAPL.NASDAQ`) or bare "
            "`data.futures` roots (for example `ES`). Each value must carry explicit "
            "`up` and `down` widths.",
        ],
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
        "### `optimization`",
        "",
        "Defines the Run's search policy and Observation Block length.",
        "",
    ]
    lines.append(_render_field_table(OptimizationConfig))
    lines.append("")

    lines.append(
        "**`observation_block_bars`** fixes the predeclared analysis duration. "
        "Aegis derives one common warmup from the sampled Component grid, uses "
        "all remaining Development rows, and merges a final remainder into the "
        "preceding block. Splitter construction and application are internal policy."
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
        "section is still required, but locked runs do not perform Candidate search.",
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
            "Missing-Index Policy",
            MISSING_POLICIES,
            "Valid values for `data.missing_index`.",
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
      base_currency: USD
      instruments: [AAPL.NASDAQ, MSFT.NASDAQ, SPY.ARCA]
      exchange: [EUR/USD.IDEALPRO]
      arrays: [OHLCV]
      start: "2024-01-01"
      end: "2024-12-31"
      timeframe: "1D"

    portfolio:
      direction: longonly
      base_currency: EUR
      band_up: 0.0
      band_down: 0.0
      band_overrides:
        AAPL.NASDAQ:
          up: 0.01
          down: 0.03

    strategy:
      id: demo.strategy

    indicators:
      - id: demo.returns

    ranking:
      metric: sharpe_ratio

    optimization:
      search: grid
      observation_block_bars: 63
    ```

    This example reads native Nautilus bars from the configured catalog/port, uses
    the `demo.strategy` and `demo.returns` Component fixtures, and fixed 63-bar
    Observation Blocks. The `demo.*` Components must exist under
    `research/components/strategies/` and `research/components/indicators/`
    relative to the working directory.""")


def _render_futures_example() -> str:
    """Embed a worked continuous-future Run Config YAML snippet."""
    return textwrap.dedent(f"""\
    ## Example: Continuous Future

    A back-adjusted continuous future declared by its bare root, alongside a raw dated
    leg. The continuous series is materialised on demand from the dated-leg chain
    (Path A) — never persisted — and its venue/currency come from the catalog legs.

    ```yaml
    schema_version: {CONFIG_SCHEMA_VERSION}
    name: example.futures

    data:
      base_currency: USD
      instruments: [ESZ6.XCME]
      futures: [ES]
      arrays: [OHLCV]
      start: "2020-01-01"
      end: "2023-12-31"
      timeframe: "1D"

    portfolio:
      direction: longonly
      base_currency: EUR
      band_up: 0.0
      band_down: 0.0
      band_overrides:
        ES:
          up: 0.03
          down: 0.08

    strategy:
      id: demo.strategy

    indicators:
      - id: demo.returns

    ranking:
      metric: sharpe_ratio

    optimization:
      search: grid
      observation_block_bars: 126
    ```

    `ESZ6.XCME` is a native Nautilus `InstrumentId` read as raw bars. `ES` is a bare
    continuous-future root: the catalog adapter builds its dated-leg chain, hands the
    roll-transition table to Nautilus's engine, and exposes the adjusted series as the
    synthetic `ES.<venue>` bundle column — `InstrumentId`-keyed like every other.""")


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
    annotations = get_type_hints(cls, include_extras=True)
    result: list[FieldDef] = []
    for f in dc_fields(cls):
        if f.name.startswith("_"):
            continue
        result.append(_field_def(f, annotation=annotations[f.name]))
    return result


def _field_def(field: DcField[Any], *, annotation: Any) -> FieldDef:
    name = field.name

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
        notes=_render_constraints(annotation),
    )


def _render_constraints(annotation: Any) -> str | None:
    """Render structural constraints from the field's Pydantic JSON Schema."""
    schema = TypeAdapter(annotation).json_schema()
    constraints: list[str] = []
    if "const" in schema:
        constraints.append(f"exactly `{schema['const']}`")
    if "minLength" in schema:
        constraints.append(f"minimum length `{schema['minLength']}`")
    if "pattern" in schema:
        constraints.append(f"must match `{schema['pattern']}`")
    excluded = schema.get("not", {}).get("enum")
    if excluded:
        values = ", ".join(f"`{value}`" for value in excluded)
        constraints.append(f"must not be {values}")
    return "; ".join(constraints) or None


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
