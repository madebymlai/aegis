"""PROTOTYPE — throwaway spike, DELETE ME. Not imported by production code.

Question it answers: if we port ONE config section (portfolio) to
``pydantic.dataclasses`` in strict mode, what does the real diff look like
against today's hand-rolled validator on the three claims that matter?

  1. SSOT requiredness   — no default ⇒ required, so the gross_cap
                           default-vs-required drift becomes unrepresentable.
  2. All-errors-at-once  — pydantic accumulates; can we map its errors back
                           to our ConfigValidationIssue(path, message) contract?
  3. Byte-identity       — does resolved_config serialization stay
                           byte-for-byte identical to the stdlib dataclass?

Run:  .venv/bin/python research/aegis_research/configuration/_prototype_pydantic_portfolio.py
Repl: .venv/bin/python research/aegis_research/configuration/_prototype_pydantic_portfolio.py --repl
"""

from __future__ import annotations

import json
import sys
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.dataclasses import dataclass as pyd_dataclass

from research.aegis_research.canonical_json import canonical_json_bytes, to_builtin
from research.aegis_research.configuration.schema import (
    ConfigValidationIssue,
    PortfolioConfig,  # the current stdlib dataclass
)
from research.aegis_research.configuration.validation.portfolio import (
    PORTFOLIO_REMOVED_FIELDS,
    _validate_portfolio,  # today's hand-rolled validator
)

# --------------------------------------------------------------------------
# The pydantic port. strict=True stops silent coercion; extra="forbid" gives
# us the closed-world "unknown field" behaviour. kw_only sidesteps field
# ordering so a required field can sit among defaulted ones (as direction does
# today). Requiredness now lives in ONE place: a field with no default IS
# required — there is no second "is required" rule to drift from.
# --------------------------------------------------------------------------
# NOTE (prototype findings):
#  - strict=True at the *model* level makes pydantic refuse to build the
#    dataclass from a dict ("Input should be an instance of ..."). Strictness
#    must be PER FIELD so dict->dataclass structuring still works.
#  - per-field constraints belong in Annotated[T, Field(...)], NOT as a default
#    value (Field(...) as a default crashes schema generation for required fields).
_StrictPos = Annotated[float, Field(gt=0, strict=True)]
_StrictNonNeg = Annotated[float, Field(ge=0, strict=True)]


@pyd_dataclass(frozen=True, kw_only=True, config=ConfigDict(extra="forbid"))
class PydPortfolioConfig:
    direction: Literal["longonly", "shortonly", "both"]  # required + enum, for free
    gross_cap: _StrictPos                                 # required (no default), positive
    init_cash: _StrictPos = 10_000.0
    fees: _StrictNonNeg = 0.001
    slippage: _StrictNonNeg = 0.0005
    net_cap: _StrictNonNeg = 1.0
    short_borrow_rate: _StrictNonNeg = 0.005
    short_rebate_rate: _StrictNonNeg = 0.0


_PYD_ADAPTER = TypeAdapter(PydPortfolioConfig)

# pydantic error-type -> our message wording, to honour the tested contract.
_MESSAGE_BY_TYPE = {
    "missing": "is required",
    "extra_forbidden": "unknown field",
}


def _issue_path(loc: tuple[Any, ...]) -> str:
    return "portfolio" + "".join(f".{part}" for part in loc)


def validate_portfolio_pydantic(raw: dict[str, Any]) -> list[ConfigValidationIssue]:
    """Map a pydantic validation pass back onto our issue list.

    Bespoke domain messages (the removed-field tombstones) stay hand-written —
    pydantic has no notion of "renamed to portfolio.gross_cap". This pre-pass
    mirrors exactly what the real validator does today, and is the honest home
    for the ~21 bespoke messages a framework can't generate.
    """
    issues: list[ConfigValidationIssue] = []
    for removed, message in PORTFOLIO_REMOVED_FIELDS.items():
        if removed in raw:
            issues.append(ConfigValidationIssue(f"portfolio.{removed}", message))

    try:
        _PYD_ADAPTER.validate_python(raw)
    except ValidationError as error:
        for err in error.errors():
            path = _issue_path(err["loc"])
            message = _MESSAGE_BY_TYPE.get(err["type"], err["msg"])
            issues.append(ConfigValidationIssue(path, message))
    return issues


def validate_portfolio_current(raw: dict[str, Any]) -> list[ConfigValidationIssue]:
    issues: list[ConfigValidationIssue] = []
    _validate_portfolio(raw, issues)
    return issues


# --------------------------------------------------------------------------
# The cattrs port. cattrs structures a dict INTO a plain stdlib dataclass — the
# serialized type never changes, so the byte oracle is protected by construction.
# Requiredness is the dataclass's own (no default ⇒ required). detailed_validation
# (default) accumulates all field errors; forbid_extra_keys gives closed-world.
# What cattrs does NOT give for a stdlib dataclass: range (gt/ge) and cross-field
# rules — those stay hand-written, exactly as today.
# --------------------------------------------------------------------------
import cattrs  # noqa: E402  (prototype: keep the cattrs port self-contained here)
from dataclasses import dataclass as std_dataclass  # noqa: E402


@std_dataclass(frozen=True, kw_only=True)
class CattrsPortfolioConfig:
    direction: Literal["longonly", "shortonly", "both"]  # required + enum (cattrs checks Literal)
    gross_cap: float                                     # required (no default) — SSOT, no drift
    init_cash: float = 10_000.0
    fees: float = 0.001
    slippage: float = 0.0005
    net_cap: float = 1.0
    short_borrow_rate: float = 0.005
    short_rebate_rate: float = 0.0


_CATTRS = cattrs.Converter(forbid_extra_keys=True, detailed_validation=True)


def validate_portfolio_cattrs(raw: dict[str, Any]) -> list[ConfigValidationIssue]:
    issues: list[ConfigValidationIssue] = []
    for removed, message in PORTFOLIO_REMOVED_FIELDS.items():
        if removed in raw:
            issues.append(ConfigValidationIssue(f"portfolio.{removed}", message))
    try:
        obj = _CATTRS.structure(raw, CattrsPortfolioConfig)
    except Exception as exc:  # ClassValidationError (ExceptionGroup)
        for msg in cattrs.transform_error(exc):
            # cattrs encodes the path INTO the message ("... @ $.gross_cap"); we
            # can't cleanly recover our flat (path, message) without string-parsing.
            issues.append(ConfigValidationIssue("portfolio", msg))
    else:
        # range checks have no cattrs home on a stdlib dataclass — hand-written:
        if obj.gross_cap <= 0:
            issues.append(ConfigValidationIssue("portfolio.gross_cap", "must be positive"))
        for name in ("fees", "slippage", "net_cap", "short_borrow_rate", "short_rebate_rate"):
            if getattr(obj, name) < 0:
                issues.append(ConfigValidationIssue(f"portfolio.{name}", "must be at least 0"))
        if obj.init_cash <= 0:
            issues.append(ConfigValidationIssue("portfolio.init_cash", "must be positive"))
    return issues


# --------------------------------------------------------------------------
# Surface state.
# --------------------------------------------------------------------------
def _fmt(issues: list[ConfigValidationIssue]) -> str:
    if not issues:
        return "    (valid — no issues)"
    return "\n".join(f"    - {i.path}: {i.message}" for i in sorted(issues, key=lambda x: x.path))


def _golden_bytes(raw: dict[str, Any]) -> str:
    """Compare canonical bytes of the stdlib build vs the pydantic and cattrs builds."""
    try:
        std_bytes = canonical_json_bytes(to_builtin(PortfolioConfig(**raw)))
    except TypeError as exc:
        return f"    stdlib build failed: {exc}"

    out: list[str] = []
    for label, build in (
        ("pydantic", lambda: _PYD_ADAPTER.validate_python(raw)),
        ("cattrs  ", lambda: _CATTRS.structure(raw, CattrsPortfolioConfig)),
    ):
        try:
            other_bytes = canonical_json_bytes(to_builtin(build()))
        except Exception:
            out.append(f"    {label}: rejected (cannot compare)")
            continue
        if other_bytes == std_bytes:
            out.append(f"    {label}: IDENTICAL")
        else:
            out.append(f"    {label}: *** DIVERGED ***")
            out.append(f"      stdlib: {std_bytes.decode()}")
            out.append(f"      {label.strip()}: {other_bytes.decode()}")
    return "\n".join(out)


SCENARIOS: list[tuple[str, dict[str, Any]]] = [
    ("valid (explicit gross_cap + direction)", {"gross_cap": 1.0, "direction": "longonly"}),
    ("THE DRIFT: gross_cap omitted", {"direction": "longonly"}),
    ("direction omitted", {"gross_cap": 1.0}),
    ("both required fields omitted (accumulate?)", {}),
    ("bad enum direction", {"gross_cap": 1.0, "direction": "sideways"}),
    ("negative gross_cap", {"gross_cap": -1.0, "direction": "both"}),
    ("multiple errors at once", {"gross_cap": "nope", "fees": -1, "direction": 5}),
    ("unknown field", {"gross_cap": 1.0, "direction": "both", "leverage": 2}),
    ("removed-field tombstone", {"gross_cap": 1.0, "direction": "both", "entry_budget": 5}),
    ("COERCION: integer gross_cap (1 not 1.0)", {"gross_cap": 1, "direction": "both"}),
    ("COERCION: bool as number", {"gross_cap": 1.0, "fees": True, "direction": "both"}),
]


def run_battery() -> None:
    for title, raw in SCENARIOS:
        print(f"\n=== {title} ===")
        print(f"  raw: {raw}")
        print("  current validator:")
        print(_fmt(validate_portfolio_current(raw)))
        print("  pydantic validator:")
        print(_fmt(validate_portfolio_pydantic(raw)))
        print("  cattrs validator:")
        print(_fmt(validate_portfolio_cattrs(raw)))
        print("  golden bytes:")
        print(_golden_bytes(raw))


def repl() -> None:
    print("Type a JSON portfolio dict (e.g. {\"gross_cap\": 1.0, \"direction\": \"both\"}). Ctrl-D to exit.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"  bad JSON: {exc}")
            continue
        print("  current :", _fmt(validate_portfolio_current(raw)).strip())
        print("  pydantic:", _fmt(validate_portfolio_pydantic(raw)).strip())
        print("  cattrs  :", _fmt(validate_portfolio_cattrs(raw)).strip())
        print("  bytes   :", _golden_bytes(raw).strip())


if __name__ == "__main__":
    if "--repl" in sys.argv:
        repl()
    else:
        run_battery()
