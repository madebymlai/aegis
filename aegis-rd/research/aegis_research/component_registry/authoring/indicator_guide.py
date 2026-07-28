"""Indicator component authoring guide.

Exports ``render_indicator_schema_guide()``, the render function for
``aerd show indicator-schema``.  The function builds a curated markdown
guide from code constants (entry-point names) plus hand-curated prose
for the manifest field table, structural rules, and semantic rules.

ADR reference: ADR-0019 (authoring contracts served by CLI, rendered
from validating models).
"""

from __future__ import annotations

from pathlib import Path

from research.aegis_research.component_registry.contracts import (
    COMPONENT_ENTRYPOINT,
    COMPONENT_PARAM_SPACE_ENTRYPOINT,
)

GUIDE_SCHEMA_VERSION = "indicator_schema_guide.v1"
"""Payload schema version for the ``aerd show indicator-schema`` JSON envelope."""


def render_indicator_schema_guide() -> str:
    """Return a complete markdown authoring guide for Indicator Components.

    The guide covers the v2 component contract (ADR-0017): percent-cell
    structure, domain-fact manifest, batched ``run`` entry point, optional
    ``param_space``, mapping-of-outputs return contract, candidate-major
    layout, and batch-invariance rule.

    The manifest field table and entry-point names are interpolated from code;
    semantic rules are curated prose.
    """
    lines: list[str] = []
    _extend_title(lines)
    _extend_percent_cell_structure(lines)
    _extend_manifest(lines)
    _extend_entry_points(lines)
    _extend_run_entry_point(lines)
    _extend_param_space(lines)
    _extend_batch_invariance(lines)
    _extend_complete_example(lines)
    return "\n".join(lines) + "\n"


def _manifest_field_table() -> str:
    """Build a markdown table of manifest fields.

    Renders the common base fields plus the Indicator-specific additions
    (``output_names``, ``bar_aligned``).
    """
    lines: list[str] = []
    lines.append("| Field | Type | Required | Default | Description |")
    lines.append("|-------|------|----------|---------|-------------|")

    # Base fields (common to Indicator and Strategy manifests)
    lines.append(
        '| `family` | `Literal["indicators"]` | yes | — | Must be the literal string `indicators` |'
    )
    lines.append(
        "| `id` | string | yes | — | "
        "Globally unique component identifier (e.g. `example.ma`); "
        "must not be `.` or `..` |"
    )
    lines.append(
        "| `version` | string | yes | — | Semantic version of this component file (e.g. `1.0.0`) |"
    )
    lines.append(
        "| `input_names` | list[string] | yes | — | "
        "VBT feature names this component reads from the run data "
        '(e.g. `["Close"]`); no surrounding whitespace or control '
        "characters |"
    )
    lines.append(
        "| `param_names` | list[string] | no | `[]` | "
        'Names of configurable parameters (e.g. `["window", "wtype"]`) |'
    )
    lines.append(
        "| `defaults` | dict | no | `{}` | "
        "Default values for params; every key must also appear in "
        "`param_names` |"
    )

    # Indicator-specific fields
    lines.append(
        "| `output_names` | list[string] | yes | — | "
        'Names of outputs this Indicator produces (e.g. `["ma"]`); '
        "must not be empty, must be unique, must be valid VBT feature "
        "names |"
    )
    lines.append(
        "| `bar_aligned` | `Literal[true]` | no | `true` | "
        "Must be `true` (only bar-aligned indicators are supported) |"
    )

    return "\n".join(lines)


def _read_example_source() -> str:
    """Read the packaged indicator example component source.

    The example lives next to this module so it can be embedded in the guide
    and round-tripped through the real registry parser.
    """
    example_path = Path(__file__).parent / "indicator_example.py"
    return example_path.read_text()


# ── section builders ─────────────────────────────────────────────────────────


def _extend_title(lines: list[str]) -> None:
    lines.append("# Indicator Component Authoring Guide")
    lines.append("")
    lines.append(
        "An **Indicator Component** is a single Python file that computes "
        "technical features "
        "for every Candidate in a batch.  The framework discovers it via "
        "the `COMPONENT_MANIFEST`, loads its `run` entry point, and validates "
        "the return value against the manifest `output_names`."
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
        "One-line description of what the component measures and its data source | "
        "yes |"
    )
    lines.append("| `# %% imports` | Standard-library and third-party imports | yes |")
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
    lines.append("| `# %% helpers` | Private helper functions (convention; not enforced) | no |")
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
        '(pydantic `extra="forbid"`) — only the fields above are accepted.'
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
    lines.append("| Entry point | Name | Required | How detected |")
    lines.append("|-------------|------|----------|--------------|")
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
        f"Every Indicator Component must define a module-level function named "
        f"`{COMPONENT_ENTRYPOINT}` with the batched signature and a docstring.  "
        f"The framework calls it once per batch of Candidates, not once per "
        f"Candidate."
    )
    lines.append("")
    _extend_run_signature(lines)
    _extend_return_contract(lines)
    _extend_candidate_major_layout(lines)


def _extend_run_signature(lines: list[str]) -> None:
    lines.append("### Signature")
    lines.append("")
    lines.append("```python")
    lines.append(f"def {COMPONENT_ENTRYPOINT}(data, *, n_candidates, **param_lists):")
    lines.append('    """Compute candidate-major indicator output for all candidates."""')
    lines.append("    ...")
    lines.append("```")
    lines.append("")
    lines.append(
        "Where `data` is a `MarketDataBundle` providing `.array(name)` access "
        "to the run's price arrays; `n_candidates` is the total number of "
        "Candidates in the batch; and `param_lists` is a mapping of parameter "
        "name to a **list** of per-Candidate values (length `n_candidates`)."
    )
    lines.append("")


def _extend_return_contract(lines: list[str]) -> None:
    lines.append("### Return Contract")
    lines.append("")
    lines.append(
        "An Indicator returns a **mapping** of output name to candidate-major "
        "NumPy array — always a mapping, even for single-output indicators.  "
        "Every key in the mapping must match a name declared in the manifest "
        "`output_names` list."
    )
    lines.append("")
    lines.append("```python")
    lines.append("return {")
    lines.append('    "output_name_a": result_a,  # np.ndarray of shape (T, C x S)')
    lines.append('    "output_name_b": result_b,  # np.ndarray of shape (T, C x S)')
    lines.append("}")
    lines.append("```")
    lines.append("")
    lines.append(
        "Where `T` is the number of time rows (must equal `len(close)`), "
        "`C` is `n_candidates`, and `S` is the number of symbols."
    )
    lines.append("")


def _extend_candidate_major_layout(lines: list[str]) -> None:
    lines.append("### Candidate-Major Block Layout")
    lines.append("")
    lines.append(
        "Every output array must be **candidate-major**: the columns are "
        "grouped by Candidate, not by symbol.  For Candidate *i* and symbol *j*, "
        "the column index is `i x S + j`."
    )
    lines.append("")
    lines.append("```python")
    lines.append("n_symbols = len(close.columns)")
    lines.append("result = np.full((len(close), n_candidates * n_symbols), np.nan)")
    lines.append("for candidate_index in range(n_candidates):")
    lines.append("    cols = slice(")
    lines.append("        candidate_index * n_symbols,")
    lines.append("        (candidate_index + 1) * n_symbols,")
    lines.append("    )")
    lines.append("    result[:, cols] = per_candidate_array")
    lines.append("```")
    lines.append("")
    lines.append(
        "The framework enforces a **shape gate** at the precompute boundary: "
        "every returned array must be exactly `(len(close), n_candidates x "
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
    lines.append('        "window": vbt.Param([10, 20, 50]),')
    lines.append('        "wtype": vbt.Param(["simple", "exp"]),')
    lines.append("    }")
    lines.append("```")
    lines.append("")


def _extend_batch_invariance(lines: list[str]) -> None:
    lines.append("## Batch-Invariance Rule")
    lines.append("")
    lines.append(
        "**Equal parameter tuples must produce bitwise-equal output blocks "
        "regardless of batch composition.**  This is a structural requirement "
        "of the v2 contract, enforced by the framework-provided self-consistency "
        "oracle."
    )
    lines.append("")
    lines.append(
        "In production the same Candidate is recomputed under different batch "
        "compositions — the full grid in continuous selection, sequential "
        "equivalence checks, and a single Candidate under Lock re-execution — "
        "so any batch-dependent float drift would make equal "
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
        "Below is a complete, validated Indicator Component (a parameterized "
        "moving-average).  It is the **authorable reference** — round-tripped "
        "through the real registry parser and the self-consistency oracle."
    )
    lines.append("")
    lines.append("```python")
    lines.append(_read_example_source())
    lines.append("```")
