"""Strategy component authoring guide.

Exports ``render_strategy_schema_guide()``, the render function for
``aerd show strategy-schema``.  The function builds a curated markdown
guide from code constants (entry-point names, allocation outputs) plus
hand-curated prose for the manifest field table, structural rules, and
semantic rules.

ADR reference: ADR-0019 (authoring contracts served by CLI, rendered
from validating models).
"""

from __future__ import annotations

from pathlib import Path

from research.aegis_research.component_registry.contracts import (
    COMPONENT_ENTRYPOINT,
    COMPONENT_PARAM_SPACE_ENTRYPOINT,
    STRATEGY_ALLOCATION_OUTPUTS,
)

GUIDE_SCHEMA_VERSION = "strategy_schema_guide.v1"
"""Payload schema version for the ``aerd show strategy-schema`` JSON envelope."""


def render_strategy_schema_guide() -> str:
    """Return a complete markdown authoring guide for Strategy Components.

    The guide covers the v2 component contract (ADR-0017): percent-cell
    structure, domain-fact manifest, batched ``run`` entry point, optional
    ``param_space``, bare allocation-array return, ``consumes_outputs`` wiring,
    inputs object, NaN-selection convention, ownership boundaries,
    and batch-invariance rule.

    The manifest field table, allocation-output catalog, and entry-point
    names are interpolated from code; semantic rules are curated prose.
    """
    lines: list[str] = []
    _extend_title(lines)
    _extend_percent_cell_structure(lines)
    _extend_manifest(lines)
    _extend_entry_points(lines)
    _extend_run_entry_point(lines)
    _extend_param_space(lines)
    _extend_nan_selection(lines)
    _extend_ownership_boundaries(lines)
    _extend_batch_invariance(lines)
    _extend_complete_example(lines)
    return "\n".join(lines) + "\n"


def _manifest_field_table() -> str:
    """Build a markdown table of manifest fields.

    Renders the common base fields plus the Strategy-specific additions
    (``output_name``, ``consumes_outputs``, ``owns_portfolio``).
    """
    lines: list[str] = []
    lines.append("| Field | Type | Required | Default | Description |")
    lines.append("|-------|------|----------|---------|-------------|")

    # Base fields (common to Indicator and Strategy manifests)
    lines.append(
        "| `family` | `Literal[\"strategies\"]` | yes | — | "
        "Must be the literal string `strategies` |"
    )
    lines.append(
        "| `id` | string | yes | — | "
        "Globally unique component identifier (e.g. `example.ma_cross`); "
        "must not be `.` or `..` |"
    )
    lines.append(
        "| `version` | string | yes | — | "
        "Semantic version of this component file (e.g. `1.0.0`) |"
    )
    lines.append(
        "| `input_names` | list[string] | yes | — | "
        "VBT feature names this component reads from the run data "
        "(e.g. `[\"Close\"]`); no surrounding whitespace or control "
        "characters |"
    )
    lines.append(
        "| `param_names` | list[string] | no | `[]` | "
        "Names of configurable parameters (e.g. `[\"fast_window\", \"slow_window\"]`) |"
    )
    lines.append(
        "| `defaults` | dict | no | `{}` | "
        "Default values for params; every key must also appear in "
        "`param_names` |"
    )

    # Strategy-specific fields
    alloc_output_list = ", ".join(f"`{o}`" for o in sorted(STRATEGY_ALLOCATION_OUTPUTS))
    lines.append(
        f"| `output_name` | `Literal[{alloc_output_list}]` | yes | — | "
        "The allocation-native channel this Strategy emits; must be one of "
        f"{alloc_output_list} |"
    )
    lines.append(
        "| `consumes_outputs` | list[string] | no | `[]` | "
        "Names of Indicator outputs this Strategy reads from "
        "`inputs.indicators` (e.g. `[\"momentum_score\", \"realized_vol\"]`); "
        "each name must be produced by a declared Indicator whose `id` appears "
        "in the Run Config |"
    )
    lines.append(
        "| `owns_portfolio` | `Literal[false]` | no | `false` | "
        "Must be `false` — portfolios are config-owned and policy-owned, "
        "not component-owned |"
    )

    return "\n".join(lines)


def _read_example_source() -> str:
    """Read the packaged strategy example component source.

    The example lives next to this module so it can be embedded in the guide
    and round-tripped through the real registry parser.
    """
    example_path = Path(__file__).parent / "strategy_example.py"
    return example_path.read_text()


# ── section builders ─────────────────────────────────────────────────────────


def _extend_title(lines: list[str]) -> None:
    lines.append("# Strategy Component Authoring Guide")
    lines.append("")
    lines.append(
        "A **Strategy Component** is a single Python file that emits an "
        "allocation-native array for every Candidate in a batch.  The "
        "framework discovers it via the `COMPONENT_MANIFEST`, loads its "
        "`run` entry point, wires its `consumes_outputs` to Indicator "
        "outputs, and passes the return value to the Allocation Policy "
        "layer for portfolio simulation."
    )
    lines.append("")


def _extend_percent_cell_structure(lines: list[str]) -> None:
    lines.append("## Percent-Cell Structure")
    lines.append("")
    lines.append(
        "Component files use `# %%` percent cells — the same delimiter Jupyter "
        "notebooks recognise for cell boundaries.  Every cell marker must "
        "include a **purpose label** (bare `# %%` is rejected).  The required "
        "cells and their canonical purposes are:"
    )
    lines.append("")
    lines.append("| Cell | Purpose | Required |")
    lines.append("|------|---------|----------|")
    lines.append(
        "| `# %% component overview` | "
        "One-line description of what the strategy does and its allocation shape | "
        "yes |"
    )
    lines.append(
        "| `# %% imports` | Standard-library and third-party imports | "
        "yes |"
    )
    lines.append(
        "| `# %% define component metadata` | "
        "The literal `COMPONENT_MANIFEST` dict (domain facts only) | "
        "yes |"
    )
    lines.append(
        f"| `# %% parameter space` | "
        f"Optional `def {COMPONENT_PARAM_SPACE_ENTRYPOINT}()` — presence-detected; "
        f"defines explorable parameter grid | "
        "no |"
    )
    lines.append(
        "| `# %% helpers` | Private helper functions (convention; not enforced) | "
        "no |"
    )
    lines.append(
        "| `# %% main compute` | "
        f"The `def {COMPONENT_ENTRYPOINT}(...)` entry point — **required** | "
        "yes |"
    )
    lines.append("")
    lines.append(
        "The `# %% main compute` cell is the **only cell whose presence is "
        "structurally enforced** (via regex match on the marker).  All other "
        "cells are enforced by convention and the AST walk (the manifest "
        f"dict, the `def {COMPONENT_ENTRYPOINT}` function, the optional "
        f"`def {COMPONENT_PARAM_SPACE_ENTRYPOINT}`)."
    )
    lines.append("")


def _extend_manifest(lines: list[str]) -> None:
    lines.append("## Manifest")
    lines.append("")
    lines.append(
        "The `COMPONENT_MANIFEST` is a **literal Python dict** at module level.  "
        "It carries **domain facts only** — the fields the framework needs to "
        "discover, validate, and wire the component.  It must be a literal "
        "(no f-strings, no computed values) so it can be read without executing "
        "the file."
    )
    lines.append("")
    lines.append("### Manifest Fields")
    lines.append("")
    lines.append(_manifest_field_table())
    lines.append("")
    lines.append(
        "Every other key in the manifest dict is **rejected at discovery time** "
        "(pydantic `extra=\"forbid\"`) — only the fields above are accepted."
    )
    lines.append("")


def _extend_entry_points(lines: list[str]) -> None:
    lines.append("## Entry Points")
    lines.append("")
    lines.append(
        "The component file contract defines exactly two possible entry points.  "
        "The entry-point names are **fixed constants**, not manifest "
        "declarations — a component file cannot rename them."
    )
    lines.append("")
    lines.append(
        "| Entry point | Name | Required | How detected |")
    lines.append(
        "|-------------|------|----------|--------------|")
    lines.append(
        f"| Batched compute | `{COMPONENT_ENTRYPOINT}` | **yes** | "
        f"`def {COMPONENT_ENTRYPOINT}` at module level; must have a docstring |"
    )
    lines.append(
        f"| Parameter space | `{COMPONENT_PARAM_SPACE_ENTRYPOINT}` | no | "
        f"`def {COMPONENT_PARAM_SPACE_ENTRYPOINT}` at module level (presence-detected in the AST walk); "
        f"its existence makes the component searchable |"
    )
    lines.append("")


def _extend_run_entry_point(lines: list[str]) -> None:
    lines.append(f"## The `{COMPONENT_ENTRYPOINT}` Entry Point")
    lines.append("")
    lines.append(
        f"Every Strategy Component must define a module-level function named "
        f"`{COMPONENT_ENTRYPOINT}` with the batched signature and a docstring.  "
        f"The framework calls it once per batch of Candidates (after all "
        f"Indicators), not once per Candidate."
    )
    lines.append("")
    _extend_run_signature(lines)
    _extend_return_contract(lines)
    _extend_inputs_object(lines)
    _extend_candidate_major_layout(lines)


def _extend_run_signature(lines: list[str]) -> None:
    lines.append("### Signature")
    lines.append("")
    lines.append("```python")
    lines.append(
        f"def {COMPONENT_ENTRYPOINT}(inputs, *, n_candidates, **param_lists):"
    )
    lines.append('    """Compute candidate-major allocation for all candidates."""')
    lines.append("    ...")
    lines.append("```")
    lines.append("")
    lines.append(
        "Unlike Indicators (which receive `data`), a Strategy receives an "
        "`inputs` object that bundles data access, Indicator outputs, and "
        "frame metadata (see **The `inputs` Object** below).  The `n_candidates` "
        "and `param_lists` arguments are identical to the Indicator contract."
    )
    lines.append("")


def _extend_return_contract(lines: list[str]) -> None:
    lines.append("### Return Contract")
    lines.append("")
    lines.append(
        "A Strategy returns a **bare NumPy array** of shape "
        "`(T, n_candidates * n_symbols)` — not a mapping.  The array is the "
        "allocation signal in the channel declared by the manifest "
        "`output_name`.  The framework passes this array directly to the "
        "Allocation Policy layer; it never wraps, renames, or transforms "
        "the return value."
    )
    lines.append("")
    lines.append("```python")
    lines.append("return result  # np.ndarray of shape (T, C x S)")
    lines.append("```")
    lines.append("")
    lines.append(
        "Where `T` is the number of time rows (must equal `len(close_window)`), "
        "`C` is `n_candidates`, and `S` is the number of symbols."
    )
    lines.append("")
    lines.append(
        "**Contrast with Indicators**: Indicators return a **mapping** "
        "(`{\"output_name\": array}`); Strategies return a **bare array**.  "
        "Wrapping the allocation array in a dict is a hard error."
    )
    lines.append("")


def _extend_inputs_object(lines: list[str]) -> None:
    lines.append("### The `inputs` Object")
    lines.append("")
    lines.append(
        "The first positional argument is an `inputs` object with these "
        "attributes:"
    )
    lines.append("")
    lines.append(
        "| Attribute | Type | Description |")
    lines.append(
        "|-----------|------|-------------|")
    lines.append(
        "| `inputs.data` | `MarketDataBundle` | "
        "Access to the run's price arrays via `.array(name)` |"
    )
    lines.append(
        "| `inputs.indicators` | `Mapping[str, np.ndarray]` | "
        "Pre-computed Indicator outputs, keyed by output name.  Each value "
        "is a candidate-major array of shape `(T, n_candidates * n_symbols)`.  "
        "**Only** outputs declared in `consumes_outputs` are guaranteed present; "
        "accessing an undeclared output is a component bug. |"
    )
    lines.append(
        "| `inputs.n_candidates` | `int` | "
        "Number of Candidates in the batch (equal to the `n_candidates` kwarg) |"
    )
    lines.append(
        "| `inputs.n_symbols` | `int` | "
        "Number of symbols in the run universe |"
    )
    lines.append(
        "| `inputs.metadata` | `dict` | "
        "Run metadata dict; carries the strategy and indicator component IDs "
        "under `strategy_id` and `indicator_ids` |"
    )
    lines.append("")
    lines.append(
        "The `consumes_outputs` field in the manifest is the **wiring contract**: "
        "every name listed there must be produced by an Indicator declared in "
        "the Run Config.  If a Strategy lists `consumes_outputs: [\"returns\"]` "
        "but no Indicator produces `\"returns\"`, the run is rejected at "
        "configuration time."
    )
    lines.append("")


def _extend_candidate_major_layout(lines: list[str]) -> None:
    lines.append("### Candidate-Major Block Layout")
    lines.append("")
    lines.append(
        "The allocation array must be **candidate-major**: the columns are "
        "grouped by Candidate, not by symbol.  For Candidate *i* and symbol *j*, "
        "the column index is `i x S + j`."
    )
    lines.append("")
    lines.append("```python")
    lines.append("n_symbols = inputs.n_symbols")
    lines.append("result = np.full((len(close), n_candidates * n_symbols), np.nan)")
    lines.append("for candidate_index in range(n_candidates):")
    lines.append("    cols = slice(")
    lines.append("        candidate_index * n_symbols,")
    lines.append("        (candidate_index + 1) * n_symbols,")
    lines.append("    )")
    lines.append("    result[:, cols] = per_candidate_allocation")
    lines.append("```")
    lines.append("")
    lines.append(
        "The framework enforces a **shape gate** at the simulation boundary: "
        "the returned array must be exactly `(len(close_window), n_candidates x "
        "n_symbols)`.  A misshapen array raises `ComponentSourceError` naming "
        "the component, expected shape, and actual shape."
    )
    lines.append("")


def _extend_param_space(lines: list[str]) -> None:
    lines.append(f"## Optional `{COMPONENT_PARAM_SPACE_ENTRYPOINT}`")
    lines.append("")
    lines.append(
        f"A component has a parameter space **iff** its module defines a function "
        f"named `{COMPONENT_PARAM_SPACE_ENTRYPOINT}`.  There is no manifest flag "
        f"for it — the AST walk detects its presence, so the file is the single "
        f"source of truth."
    )
    lines.append("")
    lines.append(
        f"The `{COMPONENT_PARAM_SPACE_ENTRYPOINT}` function takes no arguments and "
        f"returns a dict mapping parameter names to VBT `Param` objects.  When "
        f"present, all declared `param_names` are **waived** — the parameter "
        f"space defines which params are explored."
    )
    lines.append("")
    lines.append("```python")
    lines.append(f"def {COMPONENT_PARAM_SPACE_ENTRYPOINT}():")
    lines.append('    """Return VBT-native params for exploration."""')
    lines.append("    return {")
    lines.append('        "fast_window": vbt.Param([5, 10, 20]),')
    lines.append('        "slow_window": vbt.Param([30, 50, 100]),')
    lines.append("    }")
    lines.append("```")
    lines.append("")


def _extend_nan_selection(lines: list[str]) -> None:
    lines.append("## NaN-Selection Convention")
    lines.append("")
    lines.append(
        "A Strategy uses the **NaN = excluded** convention to select which "
        "symbols to allocate to at each rebalance row:"
    )
    lines.append("")
    lines.append(
        "- Allocate a **finite** value (e.g. `1.0`, `0.25`) to selected "
        "symbol columns."
    )
    lines.append(
        "- Set **`np.nan`** to excluded symbol columns — the Allocation Policy "
        "layer treats NaN as \"do not allocate to this symbol this rebalance\"."
    )
    lines.append(
        "- The component **owns** top-N filtering and gating logic (e.g. rank "
        "items, pick top-N, gate by a momentum threshold).  The Allocation "
        "Policy layer does not re-rank or re-filter — it interprets the "
        "allocations as given."
    )
    lines.append("")
    lines.append(
        "```python")
    lines.append("# Example: select only fastest-growing symbols per bar")
    lines.append("selected = fast.gt(slow)")
    lines.append("active = selected.where(selected, other=float(\"nan\")).astype(float)")
    lines.append("```")
    lines.append("")


def _extend_ownership_boundaries(lines: list[str]) -> None:
    lines.append("## Ownership Boundaries")
    lines.append("")
    lines.append(
        "A Strategy Component owns exactly its **allocation signal** — the "
        "bare array it returns.  The following are **config-owned and "
        "policy-owned**, not owned by the Strategy:"
    )
    lines.append("")
    lines.append(
        "| Concern | Owner | Config Key |")
    lines.append(
        "|----------|-------|------------|")
    lines.append(
        "| Portfolio sizing | Run Config | `portfolio.gross_cap` |"
    )
    lines.append(
        "| Direction (long/short) | Run Config | `portfolio.direction` |"
    )
    lines.append(
        "| Signal-to-order conversion | Run Config | `signal.policy`, `signal.execution_timing` |"
    )
    lines.append(
        "| Metrics (Sharpe, drawdown, etc.) | Run Config | `ranking.metric` |"
    )
    lines.append(
        "| VBT kwargs (engine, chunking) | Run Config | `optimization.execute` |"
    )
    lines.append(
        "| Split method | Run Config | `optimization.split.method` |"
    )
    lines.append(
        "| `owns_portfolio` in manifest | Manifest literal | Must be `false` — "
        "portfolio logic is not authorable in a Component |"
    )
    lines.append("")
    lines.append(
        "The manifest field `owns_portfolio` must be `false`.  A Strategy "
        "never builds a VBT `Portfolio` or computes metrics — the framework "
        "does that centrally with the Run Config settings."
    )
    lines.append("")


def _extend_batch_invariance(lines: list[str]) -> None:
    lines.append("## Batch-Invariance Rule")
    lines.append("")
    lines.append(
        "**Equal parameter tuples must produce bitwise-equal output blocks "
        "regardless of batch composition.**  This is a structural requirement "
        "of the v2 component contract, enforced by the framework-provided "
        "self-consistency oracle."
    )
    lines.append("")
    lines.append(
        "In production the same Candidate is recomputed under different batch "
        "compositions — the full grid in the selection phase, three "
        "representatives in the held-out phase, a single Candidate under a Lock "
        "re-execution — so any batch-dependent float drift would make equal "
        "parameters yield different values across phases and break Candidate "
        "reproducibility (ADR-0006)."
    )
    lines.append("")
    lines.append(
        "The invariant: calling `run` with the full Candidate batch must equal "
        "stitching-Candidates-together `run` invoked once per single-Candidate "
        "batch, **bitwise** (`np.array_equal(..., equal_nan=True)`).  NaN-aware "
        "equality is strict by design — there is no tolerance threshold."
    )
    lines.append("")


def _extend_complete_example(lines: list[str]) -> None:
    lines.append("## Complete Example")
    lines.append("")
    lines.append(
        "Below is a complete, validated Strategy Component (a parameterized "
        "moving-average crossover).  It is the **authorable reference** — "
        "round-tripped through the real registry parser and the "
        "self-consistency oracle."
    )
    lines.append("")
    lines.append("```python")
    lines.append(_read_example_source())
    lines.append("```")
